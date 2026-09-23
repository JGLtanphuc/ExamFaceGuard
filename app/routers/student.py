from fastapi import APIRouter, Depends, Request, HTTPException, status, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import os
from pydantic import BaseModel

from ..database.connection import get_db
from ..database.models import (
    CauHoi, CauTraLoi, ThiSinhTrongPhien, SinhVien, SuKienCanhBao, KyThi
)
from ..services.authentication_service import require_role, get_current_user
from ..services.session_service import get_student_session
from ..services.machine_service import set_machine_offline
from ..services.verification_service import verify_checkin_face
from ..websocket.manager import ws_manager

router = APIRouter(prefix="/student", tags=["Sinh Viên"])

templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_path)


class AnswerRequest(BaseModel):
    ma_cau_hoi: int
    dap_an: str


class VerifyFacePayload(BaseModel):
    image_base64: str


@router.get("/verify-face", response_class=HTMLResponse)
async def verify_face_page(
    request: Request,
    user: dict = Depends(require_role(["SINH_VIEN"])),
    db: Session = Depends(get_db)
):
    """Giao diện chụp ảnh xác thực khuôn mặt (Face Verification Check-in)"""
    ma_sinh_vien = user["ma_sinh_vien"]
    session_info = get_student_session(db, ma_sinh_vien)
    if not session_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin ca thi được phân bổ cho sinh viên."
        )

    # Nếu thí sinh đã xác thực thành công hoặc đã nộp bài, chuyển thẳng vào /student
    ts = db.query(ThiSinhTrongPhien).filter(
        ThiSinhTrongPhien.MaThamGia == session_info["ma_tham_gia"]
    ).first()
    if ts and ts.TrangThai in ["Dang thi", "Da nop"]:
        token = request.query_params.get("token") or request.cookies.get("access_token") or ""
        return RedirectResponse(url=f"/student?token={token}", status_code=status.HTTP_303_SEE_OTHER)

    token = request.query_params.get("token") or request.cookies.get("access_token") or ""
    return templates.TemplateResponse(
        request=request,
        name="verify_face.html",
        context={
            "user": user,
            "session": session_info,
            "token": token
        }
    )


@router.post("/api/verify-face")
async def process_face_verification(
    payload: VerifyFacePayload,
    user: dict = Depends(require_role(["SINH_VIEN"])),
    db: Session = Depends(get_db)
):
    """
    Xử lý nhận diện và so khớp khuôn mặt thí sinh với RetinaFace + FaceNet512:
    - Nếu trùng khớp (sim >= 70%): Cấp quyền vào làm bài thi, lưu ảnh check-in.
    - Nếu không trùng khớp: Chặn không cho vào thi, ghi nhận cảnh báo nghi vấn thi hộ.
    """
    ma_sinh_vien = user["ma_sinh_vien"]
    session_info = get_student_session(db, ma_sinh_vien)
    if not session_info:
        return JSONResponse({"success": False, "message": "Không tìm thấy thông tin ca thi."}, status_code=400)

    sv = db.query(SinhVien).filter(SinhVien.MaSinhVien == ma_sinh_vien).first()
    if not sv or not sv.FaceEmbedding:
        return JSONResponse({"success": False, "message": "Hồ sơ sinh viên chưa có dữ liệu khuôn mặt mẫu."}, status_code=400)

    # Lấy ngưỡng nhận diện từ kỳ thi (mặc định 0.70)
    ky_thi = db.query(KyThi).filter(KyThi.MaKyThi == session_info["ma_ky_thi"]).first()
    threshold = float(ky_thi.NguongNhanDien) if ky_thi and ky_thi.NguongNhanDien else 0.70

    # Chạy pipeline đối sánh RetinaFace + FaceNet512
    result = verify_checkin_face(
        image_base64=payload.image_base64,
        ma_sinh_vien=ma_sinh_vien,
        target_embedding_str=sv.FaceEmbedding,
        threshold=threshold
    )

    ma_tham_gia = session_info["ma_tham_gia"]
    ts = db.query(ThiSinhTrongPhien).filter(ThiSinhTrongPhien.MaThamGia == ma_tham_gia).first()

    now = datetime.utcnow()
    if result["success"]:
        if ts:
            ts.TrangThai = "Dang thi"
            ts.DoTuongDongXacThuc = result["similarity"]
            ts.AnhXacThuc = result["image_path"]
            ts.ThoiGianDangNhap = now
        db.commit()

        # Ghi nhận sự kiện xác thực thành công vào SuKienCanhBao (audit trail)
        try:
            event = SuKienCanhBao(
                MaThamGia=ma_tham_gia,
                LoaiSuKien="XAC_THUC_HOP_LE",
                DoTuongDong=result["similarity"],
                SoKhuonMat=result["num_faces"],
                ThoiGianBatDau=now,
                DuongDanSnapshot=result["image_path"],
                GhiChu=f"Xác thực hợp lệ lúc đăng nhập ({result['similarity']*100:.1f}%)"
            )
            db.add(event)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[Audit Event Note]: {e}")

        # Thông báo Giám thị qua WebSocket
        try:
            await ws_manager.broadcast_to_session(session_info["ma_phien_thi"], {
                "event": "STUDENT_VERIFIED",
                "data": {
                    "ma_tham_gia": ma_tham_gia,
                    "ma_sinh_vien": ma_sinh_vien,
                    "mssv": sv.MSSV,
                    "ho_ten": sv.HoTen,
                    "ma_pc": session_info["ma_pc"],
                    "similarity": result["similarity"],
                    "image_path": result["image_path"],
                    "thoi_gian": now.strftime("%H:%M:%S"),
                    "trang_thai": "Đang thi"
                }
            })
        except Exception as ws_err:
            print(f"[WebSocket Broadcast Error]: {ws_err}")

        return {
            "success": True,
            "similarity": result["similarity"],
            "image_path": result["image_path"],
            "redirect_url": "/student",
            "message": result["message"]
        }
    else:
        # Trường hợp không chính xác hoặc thất bại: Vẫn lưu lại ảnh check-in để Giám thị đối soát
        trang_thai_sv = "Dang xac thuc"
        if result["status"] in ["KHONG_DUNG_NGUOI", "PHAT_HIEN_NHIEU_KHUON_MAT"]:
            trang_thai_sv = "Nghi van thi ho"

        if ts:
            ts.TrangThai = trang_thai_sv
            ts.DoTuongDongXacThuc = result["similarity"]
            ts.AnhXacThuc = result["image_path"]
            ts.ThoiGianDangNhap = now
            db.commit()

        # Ghi log cảnh báo nếu không đúng người hoặc nhiều mặt
        if result["status"] in ["KHONG_DUNG_NGUOI", "PHAT_HIEN_NHIEU_KHUON_MAT"]:
            try:
                loai_sk = "KHONG_DUNG_NGUOI" if result["status"] == "KHONG_DUNG_NGUOI" else "PHAT_HIEN_NHIEU_KHUON_MAT"
                event = SuKienCanhBao(
                    MaThamGia=ma_tham_gia,
                    LoaiSuKien=loai_sk,
                    DoTuongDong=result["similarity"],
                    SoKhuonMat=result["num_faces"],
                    ThoiGianBatDau=now,
                    DuongDanSnapshot=result["image_path"],
                    GhiChu=result["message"]
                )
                db.add(event)
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"[Audit Log Warning]: {e}")

        # Bắn WebSocket cập nhật Giám thị (hiển thị ngay ảnh chụp và trạng thái mới)
        try:
            await ws_manager.broadcast_to_session(session_info["ma_phien_thi"], {
                "event": "STUDENT_VERIFY_FAILED",
                "data": {
                    "ma_tham_gia": ma_tham_gia,
                    "ma_sinh_vien": ma_sinh_vien,
                    "mssv": sv.MSSV,
                    "ho_ten": sv.HoTen,
                    "similarity": result["similarity"],
                    "image_path": result["image_path"],
                    "thoi_gian": now.strftime("%H:%M:%S"),
                    "trang_thai": "Nghi vấn thi hộ" if trang_thai_sv == "Nghi van thi ho" else "Đang xác thực"
                }
            })
        except Exception as ws_err:
            print(f"[WebSocket Broadcast Error]: {ws_err}")

        return JSONResponse({
            "success": False,
            "status": result["status"],
            "similarity": result["similarity"],
            "image_path": result["image_path"],
            "message": result["message"]
        }, status_code=400)


@router.get("", response_class=HTMLResponse)
async def student_exam_page(
    request: Request,
    user: dict = Depends(require_role(["SINH_VIEN"])),
    db: Session = Depends(get_db)
):
    """Giao diện thi trực tuyến cho sinh viên (Đã xác thực khuôn mặt thành công)"""
    ma_sinh_vien = user["ma_sinh_vien"]
    session_info = get_student_session(db, ma_sinh_vien)

    if not session_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phiên thi được phân bổ cho sinh viên này."
        )

    # Bắt buộc thí sinh phải xác thực khuôn mặt thành công trước khi vào làm bài
    ts = db.query(ThiSinhTrongPhien).filter(
        ThiSinhTrongPhien.MaThamGia == session_info["ma_tham_gia"]
    ).first()
    if not ts or ts.TrangThai not in ["Dang thi", "Da nop"]:
        token = request.query_params.get("token") or request.cookies.get("access_token") or ""
        return RedirectResponse(url=f"/student/verify-face?token={token}", status_code=status.HTTP_303_SEE_OTHER)

    # Lấy danh sách 5 câu hỏi trắc nghiệm của kỳ thi
    ma_ky_thi = session_info["ma_ky_thi"]
    cau_hoi_list = db.query(CauHoi).filter(
        CauHoi.MaKyThi == ma_ky_thi
    ).order_by(CauHoi.SoThuTu.asc()).all()

    # Lấy các câu trả lời đã lưu trước đó của thí sinh
    ma_tham_gia = session_info["ma_tham_gia"]
    da_tra_loi = db.query(CauTraLoi).filter(
        CauTraLoi.MaThamGia == ma_tham_gia
    ).all()
    dap_an_map = {ans.MaCauHoi: ans.DapAnChon for ans in da_tra_loi}

    token = request.query_params.get("token") or request.cookies.get("access_token") or ""

    return templates.TemplateResponse(
        request=request,
        name="student.html",
        context={
            "user": user,
            "session": session_info,
            "cau_hoi_list": cau_hoi_list,
            "dap_an_map": dap_an_map,
            "token": token
        }
    )


@router.post("/answer")
async def save_answer(
    data: AnswerRequest,
    user: dict = Depends(require_role(["SINH_VIEN"])),
    db: Session = Depends(get_db)
):
    """Lưu lựa chọn câu trả lời của thí sinh vào bảng CauTraLoi"""
    session_info = get_student_session(db, user["ma_sinh_vien"])
    if not session_info:
        return JSONResponse({"success": False, "message": "Không tìm thấy lượt thi"}, status_code=400)

    ma_tham_gia = session_info["ma_tham_gia"]
    existing = db.query(CauTraLoi).filter(
        CauTraLoi.MaThamGia == ma_tham_gia,
        CauTraLoi.MaCauHoi == data.ma_cau_hoi
    ).first()

    now = datetime.utcnow()
    if existing:
        existing.DapAnChon = data.dap_an
        existing.ThoiGianTraLoi = now
    else:
        new_ans = CauTraLoi(
            MaThamGia=ma_tham_gia,
            MaCauHoi=data.ma_cau_hoi,
            DapAnChon=data.dap_an,
            ThoiGianTraLoi=now
        )
        db.add(new_ans)

    db.commit()
    return {"success": True, "ma_cau_hoi": data.ma_cau_hoi, "dap_an": data.dap_an}


@router.post("/submit")
async def submit_exam(
    user: dict = Depends(require_role(["SINH_VIEN"])),
    db: Session = Depends(get_db)
):
    """Nộp bài thi, tính điểm và cập nhật trạng thái Da nop"""
    session_info = get_student_session(db, user["ma_sinh_vien"])
    if not session_info:
        return JSONResponse({"success": False, "message": "Không tìm thấy lượt thi"}, status_code=400)

    ma_tham_gia = session_info["ma_tham_gia"]
    ts = db.query(ThiSinhTrongPhien).filter(ThiSinhTrongPhien.MaThamGia == ma_tham_gia).first()

    if ts:
        ts.TrangThai = "Da nop"
        ts.ThoiGianDangXuat = datetime.utcnow()
        db.commit()

        # Tính điểm 5 câu trắc nghiệm
        ma_ky_thi = session_info["ma_ky_thi"]
        cau_hoi_list = db.query(CauHoi).filter(CauHoi.MaKyThi == ma_ky_thi).all()
        tra_loi_list = db.query(CauTraLoi).filter(CauTraLoi.MaThamGia == ma_tham_gia).all()
        user_ans = {a.MaCauHoi: a.DapAnChon for a in tra_loi_list}

        correct_count = 0
        total_count = len(cau_hoi_list)
        for ch in cau_hoi_list:
            if user_ans.get(ch.MaCauHoi) == ch.DapAnDung:
                correct_count += 1

        # Thông báo tới giám thị qua WebSocket
        await ws_manager.broadcast_to_session(session_info["ma_phien_thi"], {
            "event": "STUDENT_SUBMIT",
            "data": {
                "ma_tham_gia": ma_tham_gia,
                "ma_sinh_vien": user["ma_sinh_vien"],
                "mssv": user.get("mssv", ""),
                "trang_thai": "Đã nộp bài",
                "so_cau_dung": correct_count,
                "tong_so_cau": total_count
            }
        })

        return {
            "success": True,
            "message": "Nộp bài thành công",
            "correct_count": correct_count,
            "total_count": total_count
        }

    return JSONResponse({"success": False, "message": "Không tìm thấy thí sinh"}, status_code=404)


@router.post("/beacon-logout")
async def beacon_logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """Xử lý sự kiện sinh viên đóng tab / tắt trình duyệt (gửi qua navigator.sendBeacon)"""
    user = get_current_user(request, db)
    if user and user.get("vai_tro") == "SINH_VIEN":
        ma_sinh_vien = user.get("ma_sinh_vien")
        if ma_sinh_vien:
            ts = db.query(ThiSinhTrongPhien).filter(
                ThiSinhTrongPhien.MaSinhVien == ma_sinh_vien
            ).order_by(ThiSinhTrongPhien.MaThamGia.desc()).first()
            if ts:
                if ts.TrangThai != "Da nop":
                    ts.TrangThai = "Da dang xuat"
                ts.ThoiGianDangXuat = datetime.utcnow()
                if ts.MaMay:
                    set_machine_offline(db, ts.MaMay)
                db.commit()

                try:
                    from .monitoring import _student_session_cache
                    _student_session_cache.pop(ma_sinh_vien, None)
                except Exception:
                    pass

                await ws_manager.broadcast_to_session(ts.MaPhienThi, {
                    "event": "STUDENT_LOGOUT",
                    "data": {
                        "ma_tham_gia": ts.MaThamGia,
                        "ma_sinh_vien": ma_sinh_vien,
                        "mssv": user.get("mssv", ""),
                        "ho_ten": user.get("ho_ten", ""),
                        "trang_thai": "Đã đăng xuất"
                    }
                })
    return {"success": True}

