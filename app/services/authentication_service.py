import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from ..database.connection import get_db
from ..database.models import TaiKhoan, SinhVien

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "anti-proxy-exam-super-secure-secret-key-2026-prototype")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 giờ


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Tạo JWT Token bảo mật"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Giải mã và kiểm tra tính hợp lệ của Token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None


def authenticate_user(db: Session, identifier: str, mat_khau: str) -> Optional[TaiKhoan]:
    """
    Xác thực tài khoản và mật khẩu từ bảng TaiKhoan trong SQL Server.
    Hỗ trợ linh hoạt:
    1. Tên đăng nhập (ví dụ: 'giamthi', 'sv085')
    2. Mã số sinh viên (MSSV, ví dụ: '2001230695')
    3. Mã sinh viên (ví dụ: 'SV085')
    """
    if not identifier or not mat_khau:
        return None

    ident = identifier.strip()

    # 1. Tìm trực tiếp theo TenDangNhap trong TaiKhoan
    user = db.query(TaiKhoan).filter(
        func.lower(TaiKhoan.TenDangNhap) == ident.lower(),
        TaiKhoan.DangHoatDong == True
    ).first()

    # 2. Nếu không thấy, tìm qua MSSV hoặc MaSinhVien trong bảng SinhVien
    if not user:
        sv = db.query(SinhVien).filter(
            or_(
                SinhVien.MSSV == ident,
                func.lower(SinhVien.MaSinhVien) == ident.lower()
            )
        ).first()
        if sv and sv.MaTaiKhoan:
            user = db.query(TaiKhoan).filter(
                TaiKhoan.MaTaiKhoan == sv.MaTaiKhoan,
                TaiKhoan.DangHoatDong == True
            ).first()

    if not user:
        return None

    if user.MatKhau != mat_khau.strip():
        return None

    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[Dict[str, Any]]:
    """Lấy thông tin người dùng hiện tại từ cookie, query param hoặc Authorization header"""
    token = request.cookies.get("access_token")
    if not token:
        token = request.query_params.get("token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    payload = verify_token(token)
    if not payload:
        return None

    ma_tai_khoan = payload.get("ma_tai_khoan")
    user = db.query(TaiKhoan).filter(TaiKhoan.MaTaiKhoan == ma_tai_khoan).first()
    if not user:
        return None

    res = {
        "ma_tai_khoan": user.MaTaiKhoan,
        "ten_dang_nhap": user.TenDangNhap,
        "vai_tro": user.VaiTro
    }

    if user.VaiTro == "SINH_VIEN":
        sv = db.query(SinhVien).filter(SinhVien.MaTaiKhoan == user.MaTaiKhoan).first()
        if sv:
            res["ma_sinh_vien"] = sv.MaSinhVien
            res["mssv"] = sv.MSSV
            res["ho_ten"] = sv.HoTen

    return res


def require_role(allowed_roles: list):
    """Dependency kiểm tra quyền truy cập dựa trên vai trò"""
    def role_checker(user: Optional[Dict[str, Any]] = Depends(get_current_user)):
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Chưa đăng nhập hoặc phiên làm việc đã hết hạn"
            )
        if user.get("vai_tro") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền truy cập chức năng này"
            )
        return user
    return role_checker
