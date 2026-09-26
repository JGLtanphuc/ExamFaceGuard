from fastapi import APIRouter, Depends, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import os

from ..database.connection import get_db
from ..database.models import TaiKhoan, SinhVien, ThiSinhTrongPhien, MayTram
from ..services.authentication_service import (
    authenticate_user, create_access_token, get_current_user
)
from ..services.machine_service import get_client_ip, assign_machine_by_ip, set_machine_offline
from ..services.session_service import get_student_session
from ..websocket.manager import ws_manager

router = APIRouter()

templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_path)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Giao diện đăng nhập hệ thống (cho cả Sinh viên và Giám thị)"""
    user = get_current_user(request, db)
    if user:
        if user["vai_tro"] == "SINH_VIEN":
            ts = db.query(ThiSinhTrongPhien).filter(
                ThiSinhTrongPhien.MaSinhVien == user.get("ma_sinh_vien")
            ).first()
            if ts and ts.TrangThai == "Dang thi":
                return RedirectResponse(url="/student", status_code=status.HTTP_303_SEE_OTHER)
            return RedirectResponse(url="/student/verify-face", status_code=status.HTTP_303_SEE_OTHER)
        elif user["vai_tro"] == "GIAM_THI":
            return RedirectResponse(url="/invigilator", status_code=status.HTTP_303_SEE_OTHER)

    client_ip = get_client_ip(request)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"client_ip": client_ip, "error": None}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    response: Response,
    ten_dang_nhap: str = Form(...),
    mat_khau: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    XỬ LÝ FLOW ĐĂNG NHẬP:
    Browser -> FastAPI -> kiểm tra TaiKhoan -> kiểm tra VaiTro
    Nếu SINH_VIEN:
    -> xác định SinhVien -> tìm ThiSinhTrongPhien -> xác định PhienThi -> xác định PhongThi -> xác định CaThi
    -> lấy IP client từ request -> xác định MayTram -> kiểm tra máy thuộc đúng phòng -> gán MaMay
    -> cập nhật ThoiGianDangNhap -> cập nhật trạng thái -> /student
    Nếu GIAM_THI:
    -> /invigilator
    """
    client_ip = get_client_ip(request)

    # 1. Kiểm tra tài khoản & mật khẩu
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )

    user = authenticate_user(db, ten_dang_nhap.strip(), mat_khau.strip())
    if not user:
        if is_ajax:
            return JSONResponse({"success": False, "error": "Tên đăng nhập hoặc mật khẩu không chính xác."}, status_code=400)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"client_ip": client_ip, "error": "Tên đăng nhập hoặc mật khẩu không chính xác."},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # 2. Xử lý theo Vai Trò
    if user.VaiTro == "GIAM_THI":
        token = create_access_token({"ma_tai_khoan": user.MaTaiKhoan, "vai_tro": "GIAM_THI"})
        redirect_url = f"/invigilator?token={token}"

        is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        if is_ajax:
            res = JSONResponse({"success": True, "redirect_url": redirect_url, "token": token})
            res.set_cookie(key="access_token", value=token, max_age=3600 * 8, path="/", samesite="lax", secure=is_https)
            return res

        redirect_res = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
        redirect_res.set_cookie(
            key="access_token",
            value=token,
            max_age=3600 * 8,
            path="/",
            samesite="lax",
            secure=is_https
        )
        return redirect_res

    elif user.VaiTro == "SINH_VIEN":
        # Xác định hồ sơ sinh viên
        sv = db.query(SinhVien).filter(SinhVien.MaTaiKhoan == user.MaTaiKhoan).first()
        if not sv:
            error_msg = "Không tìm thấy thông tin hồ sơ sinh viên liên kết với tài khoản này."
            if is_ajax:
                return JSONResponse({"success": False, "error": error_msg}, status_code=400)
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"client_ip": client_ip, "error": error_msg},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # CƠ CHẾ GÁN MÁY THEO IP TỰ ĐỘNG
        success, message, machine_info = assign_machine_by_ip(db, sv.MaSinhVien, client_ip)
        if not success:
            if is_ajax:
                return JSONResponse({"success": False, "error": message}, status_code=400)
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"client_ip": client_ip, "error": message},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Cập nhật trạng thái 'Dang xac thuc' cho thí sinh
        ts = db.query(ThiSinhTrongPhien).filter(
            ThiSinhTrongPhien.MaSinhVien == sv.MaSinhVien
        ).first()
        if ts and ts.TrangThai != "Da nop":
            ts.TrangThai = "Dang xac thuc"
            db.commit()

        # Lấy thông tin phiên thi để gửi thông báo realtime cho Giám thị
        session_info = get_student_session(db, sv.MaSinhVien)
        if session_info:
            await ws_manager.broadcast_to_session(session_info["ma_phien_thi"], {
                "event": "STUDENT_LOGIN",
                "data": {
                    "ma_tham_gia": session_info["ma_tham_gia"],
                    "ma_sinh_vien": sv.MaSinhVien,
                    "mssv": sv.MSSV,
                    "ho_ten": sv.HoTen,
                    "ma_pc": machine_info["ma_pc"] if machine_info else "Chưa xác định",
                    "ten_may": machine_info["ten_may"] if machine_info else "Chưa xác định",
                    "dia_chi_ip": client_ip,
                    "trang_thai": "Đang xác thực"
                }
            })

        # Tạo token đăng nhập
        token = create_access_token({
            "ma_tai_khoan": user.MaTaiKhoan,
            "vai_tro": "SINH_VIEN",
            "ma_sinh_vien": sv.MaSinhVien
        })

        redirect_url = f"/student/verify-face?token={token}"

        is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        if is_ajax:
            res = JSONResponse({"success": True, "redirect_url": redirect_url, "token": token})
            res.set_cookie(key="access_token", value=token, max_age=3600 * 8, path="/", samesite="lax", secure=is_https)
            return res

        redirect_res = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
        redirect_res.set_cookie(
            key="access_token",
            value=token,
            max_age=3600 * 8,
            path="/",
            samesite="lax",
            secure=is_https
        )
        return redirect_res

    if is_ajax:
        return JSONResponse({"success": False, "error": "Vai trò tài khoản không hợp lệ."}, status_code=403)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"client_ip": client_ip, "error": "Vai trò tài khoản không hợp lệ."},
        status_code=status.HTTP_403_FORBIDDEN
    )


@router.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """Đăng xuất tài khoản, chuyển máy trạm về Ngoại tuyến và cập nhật trạng thái thí sinh về Đã đăng xuất"""
    user = get_current_user(request, db)
    if user and user.get("vai_tro") == "SINH_VIEN":
        ma_sinh_vien = user.get("ma_sinh_vien")
        if ma_sinh_vien:
            ts = db.query(ThiSinhTrongPhien).filter(
                ThiSinhTrongPhien.MaSinhVien == ma_sinh_vien
            ).order_by(ThiSinhTrongPhien.MaThamGia.desc()).first()
            if ts:
                # Nếu chưa nộp bài thì chuyển thành Đã đăng xuất
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

                phien = ts.MaPhienThi
                await ws_manager.broadcast_to_session(phien, {
                    "event": "STUDENT_LOGOUT",
                    "data": {
                        "ma_tham_gia": ts.MaThamGia,
                        "ma_sinh_vien": ma_sinh_vien,
                        "mssv": user.get("mssv", ""),
                        "ho_ten": user.get("ho_ten", ""),
                        "trang_thai": "Đã đăng xuất"
                    }
                })

    res = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie("access_token")
    return res
