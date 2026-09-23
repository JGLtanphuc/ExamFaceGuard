from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from ..database.models import (
    ThiSinhTrongPhien, PhienThi, PhongThi, CaThi, KyThi, SinhVien, MayTram
)


def get_student_session(db: Session, ma_sinh_vien: str) -> Optional[Dict[str, Any]]:
    """
    Xác định phiên thi, phòng thi, ca thi và kỳ thi của sinh viên dựa trên cơ sở dữ liệu.
    Sinh viên không được tự chọn phiên thi, server tự động phân giải.
    """
    record = db.query(ThiSinhTrongPhien).filter(
        ThiSinhTrongPhien.MaSinhVien == ma_sinh_vien
    ).first()

    if not record:
        return None

    phien_thi = db.query(PhienThi).filter(PhienThi.MaPhienThi == record.MaPhienThi).first()
    if not phien_thi:
        return None

    phong = db.query(PhongThi).filter(PhongThi.MaPhong == phien_thi.MaPhong).first()
    ca = db.query(CaThi).filter(CaThi.MaCa == phien_thi.MaCa).first()
    ky = db.query(KyThi).filter(KyThi.MaKyThi == phien_thi.MaKyThi).first()
    may = db.query(MayTram).filter(MayTram.MaMay == record.MaMay).first() if record.MaMay else None

    return {
        "ma_tham_gia": record.MaThamGia,
        "ma_phien_thi": phien_thi.MaPhienThi,
        "ma_ky_thi": ky.MaKyThi if ky else None,
        "ten_ky_thi": ky.TenKyThi if ky else "",
        "ma_phong": phong.MaPhong if phong else None,
        "ten_phong": phong.TenPhong if phong else "",
        "ma_ca": ca.MaCa if ca else None,
        "ten_ca": ca.TenCa if ca else "",
        "gio_bat_dau": str(ca.GioBatDau) if ca else "",
        "gio_ket_thuc": str(ca.GioKetThuc) if ca else "",
        "ma_may": record.MaMay,
        "ma_pc": may.MaPC if may else "Chưa xác định",
        "ten_may": may.TenMay if may else "Chưa xác định",
        "trang_thai": record.TrangThai,
        "anh_xac_thuc": record.AnhXacThuc,
        "do_tuong_dong_xac_thuc": float(record.DoTuongDongXacThuc) if record.DoTuongDongXacThuc is not None else None,
        "nguong_nhan_dien": float(ky.NguongNhanDien) if ky else 0.70,
        "thoi_gian_khong_co_mat": ky.ThoiGianKhongCoMatGiay if ky else 3,
        "so_lan_sai_lien_tiep": ky.SoLanSaiLienTiep if ky else 3,
        "thoi_gian_nhieu_khuon_mat": ky.ThoiGianNhieuKhuonMatGiay if ky else 2
    }


def get_session_by_room_and_shift(db: Session, ma_phong: int, ma_ca: int) -> Optional[PhienThi]:
    """Tìm phiên thi dựa trên phòng và ca thi đã chọn"""
    return db.query(PhienThi).filter(
        PhienThi.MaPhong == ma_phong,
        PhienThi.MaCa == ma_ca
    ).first()


def get_candidates_in_session(db: Session, ma_phien_thi: int) -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả thí sinh trong phiên thi phục vụ GridView Giám thị"""
    records = db.query(
        ThiSinhTrongPhien, SinhVien, MayTram
    ).join(
        SinhVien, SinhVien.MaSinhVien == ThiSinhTrongPhien.MaSinhVien
    ).outerjoin(
        MayTram, MayTram.MaMay == ThiSinhTrongPhien.MaMay
    ).filter(
        ThiSinhTrongPhien.MaPhienThi == ma_phien_thi
    ).order_by(
        SinhVien.STT
    ).all()

    results = []
    for ts, sv, mt in records:
        results.append({
            "ma_tham_gia": ts.MaThamGia,
            "ma_sinh_vien": sv.MaSinhVien,
            "mssv": sv.MSSV,
            "ho_ten": sv.HoTen,
            "stt": sv.STT,
            "ma_may": ts.MaMay,
            "ma_pc": mt.MaPC if mt else "Chưa xác định",
            "ten_may": mt.TenMay if mt else "Chưa xác định",
            "dia_chi_ip": mt.DiaChiIP if mt else None,
            "trang_thai_may": mt.TrangThai if mt else "Ngoai tuyen",
            "trang_thai_thi_sinh": ts.TrangThai,
            "thoi_gian_dang_nhap": ts.ThoiGianDangNhap.strftime("%H:%M:%S") if ts.ThoiGianDangNhap else None,
            "do_tuong_dong_xac_thuc": float(ts.DoTuongDongXacThuc) if ts.DoTuongDongXacThuc is not None else None,
            "anh_xac_thuc": ts.AnhXacThuc
        })

    return results

