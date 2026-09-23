from fastapi import APIRouter, Depends, Request, HTTPException, status, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os

from ..database.connection import get_db
from ..database.models import PhongThi, CaThi, KyThi, PhienThi
from ..services.authentication_service import require_role
from ..services.session_service import get_session_by_room_and_shift, get_candidates_in_session

router = APIRouter(prefix="/invigilator", tags=["Giám Thị"])

templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_path)


@router.get("", response_class=HTMLResponse)
async def invigilator_dashboard(
    request: Request,
    room_id: int = Query(None),
    shift_id: int = Query(None),
    user: dict = Depends(require_role(["GIAM_THI"])),
    db: Session = Depends(get_db)
):
    """
    DASHBOARD GIÁM THỊ:
    - Dropdown chọn Phòng thi (P101, P102, P103) và Ca thi (Ca 1, Ca 2, Ca 3)
    - GridView hiển thị tất cả thẻ card sinh viên trong phiên
    - Cập nhật thời gian thực bằng WebSocket
    """
    rooms = db.query(PhongThi).order_by(PhongThi.MaPhong.asc()).all()
    shifts = db.query(CaThi).order_by(CaThi.MaCa.asc()).all()

    # Mặc định chọn phòng đầu tiên và ca đầu tiên nếu chưa chọn
    selected_room = room_id or (rooms[0].MaPhong if rooms else 1)
    selected_shift = shift_id or (shifts[0].MaCa if shifts else 1)

    phien_thi = get_session_by_room_and_shift(db, selected_room, selected_shift)

    phong = db.query(PhongThi).filter(PhongThi.MaPhong == selected_room).first()
    ca = db.query(CaThi).filter(CaThi.MaCa == selected_shift).first()
    ten_phong = phong.TenPhong if phong else f"Phòng {selected_room}"
    ten_ca = ca.TenCa if ca else f"Ca {selected_shift}"

    candidates = []
    session_data = {
        "ma_phien_thi": None,
        "ten_ky_thi": "",
        "ten_phong": ten_phong,
        "ten_ca": ten_ca,
        "gio_bat_dau": str(ca.GioBatDau) if ca else "",
        "gio_ket_thuc": str(ca.GioKetThuc) if ca else "",
        "so_luong_sv": 0,
        "trang_thai": "Chua dien ra",
        "nguong_nhan_dien": 0.70
    }

    if phien_thi:
        candidates = get_candidates_in_session(db, phien_thi.MaPhienThi)
        ky = db.query(KyThi).filter(KyThi.MaKyThi == phien_thi.MaKyThi).first()
        session_data.update({
            "ma_phien_thi": phien_thi.MaPhienThi,
            "ten_ky_thi": ky.TenKyThi if ky else "",
            "so_luong_sv": len(candidates),
            "trang_thai": phien_thi.TrangThai,
            "nguong_nhan_dien": float(ky.NguongNhanDien) if ky else 0.70
        })

    return templates.TemplateResponse(
        request=request,
        name="invigilator.html",
        context={
            "user": user,
            "rooms": rooms,
            "shifts": shifts,
            "selected_room": selected_room,
            "selected_shift": selected_shift,
            "session": session_data,
            "candidates": candidates,
            "token": request.query_params.get("token") or request.cookies.get("access_token") or ""
        }
    )


@router.get("/api/session-candidates")
async def get_candidates_api(
    room_id: int = Query(...),
    shift_id: int = Query(...),
    user: dict = Depends(require_role(["GIAM_THI"])),
    db: Session = Depends(get_db)
):
    """API chuyển đổi phòng/ca thi và tải danh sách sinh viên không cần load lại trang"""
    phong = db.query(PhongThi).filter(PhongThi.MaPhong == room_id).first()
    ca = db.query(CaThi).filter(CaThi.MaCa == shift_id).first()
    ten_phong = phong.TenPhong if phong else f"Phòng {room_id}"
    ten_ca = ca.TenCa if ca else f"Ca {shift_id}"

    phien_thi = get_session_by_room_and_shift(db, room_id, shift_id)
    if not phien_thi:
        return JSONResponse({
            "success": False,
            "ten_phong": ten_phong,
            "ten_ca": ten_ca,
            "message": f"Không có phiên thi cho {ten_phong} và {ten_ca}.",
            "candidates": []
        })

    candidates = get_candidates_in_session(db, phien_thi.MaPhienThi)
    return {
        "success": True,
        "ten_phong": ten_phong,
        "ten_ca": ten_ca,
        "ma_phien_thi": phien_thi.MaPhienThi,
        "candidates": candidates
    }
