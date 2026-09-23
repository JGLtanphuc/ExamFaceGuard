import cv2
import base64
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import asyncio
from typing import Optional, Set, Dict

from ..database.connection import get_db, SessionLocal
from ..database.models import SinhVien, ThiSinhTrongPhien, KyThi, PhienThi, MayTram
from ..services.authentication_service import require_role
from ..services.face_service import decode_base64_image, parse_db_embedding, process_face_pipeline
from ..services.monitoring_service import evaluate_and_update_monitoring, get_or_create_state
from ..services.session_service import get_student_session
from starlette.concurrency import run_in_threadpool
from ..websocket.manager import ws_manager

router = APIRouter(tags=["Giám Sát AI & Realtime"])

# Tập hợp các sinh viên đang có tác vụ AI chạy nền
_active_ai_tasks: Set[str] = set()


class FramePayload(BaseModel):
    image_base64: str


# Cache thông tin phiên thi & FaceEmbedding của sinh viên để tăng tốc độ stream video
_student_session_cache: Dict[str, dict] = {}


async def _run_ai_pipeline_background(
    img,
    target_embedding: list,
    threshold: float,
    ma_tham_gia: int,
    ma_phien_thi: int,
    ma_sinh_vien: str,
    mssv: str,
    ho_ten: str,
    ma_pc: str,
    cfg_no_face: int,
    cfg_mismatch: int,
    cfg_multi: int
):
    """Worker chạy nền AI (RetinaFace + FaceNet512) - Chỉ cập nhật trạng thái & điểm tương đồng bên dưới, không vẽ khung lên video"""
    try:
        result = await run_in_threadpool(process_face_pipeline, img, target_embedding, threshold)

        with SessionLocal() as bg_db:
            await evaluate_and_update_monitoring(
                db=bg_db,
                ma_tham_gia=ma_tham_gia,
                ma_phien_thi=ma_phien_thi,
                ma_sinh_vien=ma_sinh_vien,
                mssv=mssv,
                ho_ten=ho_ten,
                ma_pc=ma_pc,
                raw_status=result["status"],
                similarity=result["similarity"],
                num_faces=result["num_faces"],
                frame_b64=None,  # Không gửi đè frame ảnh lên luồng video, để video hiển thị liên tục mượt mà không giật
                cfg_no_face_seconds=cfg_no_face,
                cfg_mismatch_count=cfg_mismatch,
                cfg_multi_face_seconds=cfg_multi
            )
    except Exception as e:
        print(f"[Monitoring AI Background] Lỗi xử lý frame: {e}")
    finally:
        # Cooldown ngắn (1.0s) để giải phóng CPU cho các luồng mạng và WebSocket
        await asyncio.sleep(1.0)
        _active_ai_tasks.discard(ma_sinh_vien)


@router.post("/api/monitoring/frame")
async def process_student_frame(
    payload: FramePayload,
    user: dict = Depends(require_role(["SINH_VIEN"])),
    db: Session = Depends(get_db)
):
    """
    ENDPOINT TIẾP NHẬN VÀ STREAM VIDEO SIÊU TỐC TỪ CAMERA SINH VIÊN:
    - Decoupled Pipeline: Stream video tức thì (< 15ms) sang Giám thị qua WebSocket.
    - AI (RetinaFace + FaceNet512) chạy nền ngầm định kỳ, không làm giật lag video.
    """
    ma_sinh_vien = user["ma_sinh_vien"]

    # 1. Lấy thông tin sinh viên từ cache (hoặc truy vấn CSDL nếu chưa có trong cache)
    cached = _student_session_cache.get(ma_sinh_vien)
    if not cached:
        sv = db.query(SinhVien).filter(SinhVien.MaSinhVien == ma_sinh_vien).first()
        if not sv or not sv.FaceEmbedding:
            return JSONResponse({
                "status": "LOI_DATABASE",
                "message": "Không tìm thấy FaceEmbedding của sinh viên",
                "similarity": 0.0,
                "num_faces": 0
            }, status_code=400)

        target_embedding = parse_db_embedding(sv.FaceEmbedding)
        if not target_embedding:
            return JSONResponse({
                "status": "LOI_DATABASE",
                "message": "Lỗi định dạng vector FaceEmbedding",
                "similarity": 0.0,
                "num_faces": 0
            }, status_code=500)

        session_info = get_student_session(db, ma_sinh_vien)
        if not session_info:
            return JSONResponse({"status": "LOI_PHIEN", "message": "Chưa có phiên thi"}, status_code=400)

        cached = {
            "mssv": sv.MSSV,
            "ho_ten": sv.HoTen,
            "target_embedding": target_embedding,
            "ma_tham_gia": session_info["ma_tham_gia"],
            "ma_phien_thi": session_info["ma_phien_thi"],
            "ma_pc": session_info["ma_pc"],
            "threshold": session_info["nguong_nhan_dien"],
            "cfg_no_face": session_info["thoi_gian_khong_co_mat"],
            "cfg_mismatch": session_info["so_lan_sai_lien_tiep"],
            "cfg_multi": session_info["thoi_gian_nhieu_khuon_mat"]
        }
        _student_session_cache[ma_sinh_vien] = cached

    # 2. STREAM VIDEO TỨC THÌ SANG GIÁM THỊ (< 15ms độ trễ, không decode base64 -> cực nhẹ)
    await ws_manager.broadcast_to_session(cached["ma_phien_thi"], {
        "event": "STUDENT_FRAME_STREAM",
        "data": {
            "ma_sinh_vien": ma_sinh_vien,
            "mssv": cached["mssv"],
            "ho_ten": cached["ho_ten"],
            "ma_pc": cached["ma_pc"],
            "frame_preview": payload.image_base64
        }
    })

    # 3. KÍCH HOẠT NHẬN DIỆN AI NẾU WORKER ĐANG RẢNH
    # Chỉ giải mã ảnh numpy khi AI worker rảnh và bắt đầu tính toán
    if ma_sinh_vien not in _active_ai_tasks:
        img = decode_base64_image(payload.image_base64)
        if img is not None:
            _active_ai_tasks.add(ma_sinh_vien)
            asyncio.create_task(_run_ai_pipeline_background(
                img=img,
                target_embedding=cached["target_embedding"],
                threshold=cached["threshold"],
                ma_tham_gia=cached["ma_tham_gia"],
                ma_phien_thi=cached["ma_phien_thi"],
                ma_sinh_vien=ma_sinh_vien,
                mssv=cached["mssv"],
                ho_ten=cached["ho_ten"],
                ma_pc=cached["ma_pc"],
                cfg_no_face=cached["cfg_no_face"],
                cfg_mismatch=cached["cfg_mismatch"],
                cfg_multi=cached["cfg_multi"]
            ))

    # 4. TRẢ VỀ PHẢN HỒI SIÊU TỐC CHO THÍ SINH (< 5ms)
    state = get_or_create_state(cached["ma_tham_gia"])
    return {
        "status": state.last_status if state.last_status != "Chua dang nhap" else "Đang giám sát",
        "similarity": state.last_similarity,
        "num_faces": state.last_num_faces,
        "is_alert": False,
        "alert_message": "",
        "bbox": None
    }


@router.websocket("/ws/monitoring/{ma_phien_thi}")
async def websocket_monitoring_endpoint(websocket: WebSocket, ma_phien_thi: int):
    """Kênh WebSocket kết nối realtime giữa server và Dashboard giám thị theo từng phiên thi"""
    await ws_manager.connect_invigilator(websocket, ma_phien_thi)
    try:
        while True:
            # Lắng nghe ping / message từ client (nếu có)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect_invigilator(websocket, ma_phien_thi)
    except Exception:
        ws_manager.disconnect_invigilator(websocket, ma_phien_thi)

