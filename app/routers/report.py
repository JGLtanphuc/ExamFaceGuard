from fastapi import APIRouter, Depends, Request, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os

from ..database.connection import get_db
from ..database.models import PhongThi, CaThi
from ..services.authentication_service import require_role
from ..services.session_service import get_session_by_room_and_shift
from ..services.report_service import get_session_report, generate_excel_report

router = APIRouter(prefix="/invigilator/report", tags=["Báo Cáo Thống Kê"])

templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_path)


@router.get("", response_class=HTMLResponse)
async def report_page(
    request: Request,
    room_id: int = Query(None),
    shift_id: int = Query(None),
    user: dict = Depends(require_role(["GIAM_THI"])),
    db: Session = Depends(get_db)
):
    """Giao diện báo cáo thống kê phòng thi sau khi kết thúc phiên thi"""
    rooms = db.query(PhongThi).order_by(PhongThi.MaPhong.asc()).all()
    shifts = db.query(CaThi).order_by(CaThi.MaCa.asc()).all()

    selected_room = room_id or (rooms[0].MaPhong if rooms else 1)
    selected_shift = shift_id or (shifts[0].MaCa if shifts else 1)

    phien_thi = get_session_by_room_and_shift(db, selected_room, selected_shift)
    report_data = {}
    if phien_thi:
        report_data = get_session_report(db, phien_thi.MaPhienThi)

    return templates.TemplateResponse(
        request=request,
        name="report.html",
        context={
            "user": user,
            "rooms": rooms,
            "shifts": shifts,
            "selected_room": selected_room,
            "selected_shift": selected_shift,
            "report": report_data
        }
    )


@router.get("/api/data")
async def report_api_data(
    room_id: int = Query(...),
    shift_id: int = Query(...),
    user: dict = Depends(require_role(["GIAM_THI"])),
    db: Session = Depends(get_db)
):
    """API lấy dữ liệu thống kê báo cáo theo phòng và ca thi"""
    phien_thi = get_session_by_room_and_shift(db, room_id, shift_id)
    if not phien_thi:
        return JSONResponse({"success": False, "message": "Không tìm thấy phiên thi"})

    report_data = get_session_report(db, phien_thi.MaPhienThi)
    return {"success": True, "report": report_data}


@router.post("/export-excel")
async def export_excel_report(
    request: Request,
    user: dict = Depends(require_role(["GIAM_THI"])),
    db: Session = Depends(get_db)
):
    """Xuất file Excel (.xlsx) các sự kiện vi phạm với định dạng các cột rõ ràng, chuẩn đẹp"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    room_id = body.get("room_id")
    shift_id = body.get("shift_id")
    events = body.get("events")

    report_data = {}
    if room_id and shift_id:
        phien_thi = get_session_by_room_and_shift(db, int(room_id), int(shift_id))
        if phien_thi:
            report_data = get_session_report(db, phien_thi.MaPhienThi)

    if not report_data:
        report_data = {
            "ten_phong": body.get("ten_phong", "PhongThi"),
            "ten_ca": body.get("ten_ca", "CaThi"),
            "gio_thi": body.get("gio_thi", "--"),
            "danh_sach_su_kien": events or []
        }

    buf = generate_excel_report(report_data, events)
    ten_phong_slug = (report_data.get("ten_phong") or "PhongThi").replace(" ", "_")
    ten_ca_slug = (report_data.get("ten_ca") or "CaThi").replace(" ", "_")
    filename = f"BienBan_DiemDanh_XacThuc_{ten_phong_slug}_{ten_ca_slug}.xlsx"

    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/export-excel")
async def export_excel_report_get(
    room_id: int = Query(...),
    shift_id: int = Query(...),
    user: dict = Depends(require_role(["GIAM_THI"])),
    db: Session = Depends(get_db)
):
    """Xuất file Excel (.xlsx) theo URL GET trực tiếp"""
    phien_thi = get_session_by_room_and_shift(db, room_id, shift_id)
    if not phien_thi:
        return JSONResponse({"success": False, "message": "Không tìm thấy phiên thi"})

    report_data = get_session_report(db, phien_thi.MaPhienThi)
    buf = generate_excel_report(report_data)
    ten_phong_slug = (report_data.get("ten_phong") or "PhongThi").replace(" ", "_")
    ten_ca_slug = (report_data.get("ten_ca") or "CaThi").replace(" ", "_")
    filename = f"BienBan_DiemDanh_XacThuc_{ten_phong_slug}_{ten_ca_slug}.xlsx"

    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
