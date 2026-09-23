from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from ..database.models import SuKienCanhBao


def record_alert_event(
    db: Session,
    ma_tham_gia: int,
    loai_su_kien: str,
    do_tuong_dong: Optional[float] = None,
    so_khuon_mat: int = 0,
    thoi_luong_giay: Optional[int] = None,
    snapshot_path: Optional[str] = None,
    ghi_chu: Optional[str] = None
) -> SuKienCanhBao:
    """
    Lưu sự kiện cảnh báo vào bảng SuKienCanhBao trong SQL Server.
    Các loại sự kiện hợp lệ:
    - 'KHONG_DUNG_NGUOI'
    - 'KHONG_PHAT_HIEN_KHUON_MAT'
    - 'PHAT_HIEN_NHIEU_KHUON_MAT'
    - 'LOI_CAMERA'
    """
    valid_types = {
        "KHONG_DUNG_NGUOI",
        "KHONG_PHAT_HIEN_KHUON_MAT",
        "PHAT_HIEN_NHIEU_KHUON_MAT",
        "LOI_CAMERA"
    }

    if loai_su_kien not in valid_types:
        raise ValueError(f"Loại sự kiện không hợp lệ: {loai_su_kien}")

    now = datetime.utcnow()
    event = SuKienCanhBao(
        MaThamGia=ma_tham_gia,
        LoaiSuKien=loai_su_kien,
        DoTuongDong=do_tuong_dong,
        SoKhuonMat=so_khuon_mat,
        ThoiGianBatDau=now,
        ThoiGianKetThuc=now,
        ThoiLuongGiay=thoi_luong_giay or 1,
        DuongDanSnapshot=snapshot_path,
        GhiChu=ghi_chu
    )

    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_candidate_alert_history(db: Session, ma_tham_gia: int):
    """Lấy lịch sử cảnh báo của 1 thí sinh"""
    return db.query(SuKienCanhBao).filter(
        SuKienCanhBao.MaThamGia == ma_tham_gia
    ).order_by(SuKienCanhBao.ThoiGianBatDau.desc()).all()


def get_session_alerts(db: Session, ma_phien_thi: int):
    """Lấy tất cả cảnh báo trong 1 phiên thi"""
    from ..database.models import ThiSinhTrongPhien, SinhVien
    return db.query(
        SuKienCanhBao, SinhVien
    ).join(
        ThiSinhTrongPhien, ThiSinhTrongPhien.MaThamGia == SuKienCanhBao.MaThamGia
    ).join(
        SinhVien, SinhVien.MaSinhVien == ThiSinhTrongPhien.MaSinhVien
    ).filter(
        ThiSinhTrongPhien.MaPhienThi == ma_phien_thi
    ).order_by(
        SuKienCanhBao.ThoiGianBatDau.desc()
    ).all()

