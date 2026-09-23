from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, DateTime,
    Date, Time, Numeric, ForeignKey, Index, Unicode
)
from sqlalchemy.orm import relationship
from .connection import Base


class TaiKhoan(Base):
    __tablename__ = "TaiKhoan"

    MaTaiKhoan = Column(Integer, primary_key=True, autoincrement=True)
    TenDangNhap = Column(String(50), unique=True, nullable=False)
    MatKhau = Column(String(255), nullable=False)
    VaiTro = Column(String(20), nullable=False)  # 'SINH_VIEN', 'GIAM_THI'
    DangHoatDong = Column(Boolean, default=True, nullable=False)
    NgayTao = Column(DateTime, default=datetime.utcnow, nullable=False)

    sinh_vien = relationship("SinhVien", back_populates="tai_khoan", uselist=False)


class SinhVien(Base):
    __tablename__ = "SinhVien"

    MaSinhVien = Column(String(10), primary_key=True)
    STT = Column(Integer, unique=True, nullable=False)
    MSSV = Column(String(30), nullable=False)
    HoTen = Column(String(150), nullable=False)
    MaTaiKhoan = Column(Integer, ForeignKey("TaiKhoan.MaTaiKhoan"), unique=True, nullable=False)
    FaceEmbedding = Column(Text, nullable=False)  # JSON 512 float
    NgayTao = Column(DateTime, default=datetime.utcnow, nullable=False)

    tai_khoan = relationship("TaiKhoan", back_populates="sinh_vien")
    danh_sach_tham_gia = relationship("ThiSinhTrongPhien", back_populates="sinh_vien")


class PhongThi(Base):
    __tablename__ = "PhongThi"

    MaPhong = Column(Integer, primary_key=True, autoincrement=True)
    TenPhong = Column(String(20), unique=True, nullable=False)
    SucChua = Column(Integer, default=30, nullable=False)
    MoTa = Column(String(200), nullable=True)

    may_tram = relationship("MayTram", back_populates="phong_thi")
    phien_thi = relationship("PhienThi", back_populates="phong_thi")


class CaThi(Base):
    __tablename__ = "CaThi"

    MaCa = Column(Integer, primary_key=True, autoincrement=True)
    TenCa = Column(String(50), unique=True, nullable=False)
    GioBatDau = Column(Time, nullable=False)
    GioKetThuc = Column(Time, nullable=False)

    phien_thi = relationship("PhienThi", back_populates="ca_thi")


class KyThi(Base):
    __tablename__ = "KyThi"

    MaKyThi = Column(Integer, primary_key=True, autoincrement=True)
    MaKyThiCode = Column(String(30), unique=True, nullable=False)
    TenKyThi = Column(String(200), nullable=False)
    NgayThi = Column(Date, nullable=False)
    TrangThai = Column(String(30), default="Chua dien ra", nullable=False)
    NguongNhanDien = Column(Numeric(6, 4), default=0.6000, nullable=False)
    ThoiGianKhongCoMatGiay = Column(Integer, default=3, nullable=False)
    SoLanSaiLienTiep = Column(Integer, default=3, nullable=False)
    ThoiGianNhieuKhuonMatGiay = Column(Integer, default=2, nullable=False)

    phien_thi = relationship("PhienThi", back_populates="ky_thi")
    cau_hoi = relationship("CauHoi", back_populates="ky_thi")


class MayTram(Base):
    __tablename__ = "MayTram"

    MaMay = Column(Integer, primary_key=True, autoincrement=True)
    MaPhong = Column(Integer, ForeignKey("PhongThi.MaPhong"), nullable=False)
    MaPC = Column(String(20), nullable=False)
    TenMay = Column(String(100), nullable=False)
    DiaChiIP = Column(String(45), nullable=True)
    TrangThai = Column(String(20), default="Ngoai tuyen", nullable=False)  # 'Online', 'Ngoai tuyen'
    LanCuoiKetNoi = Column(DateTime, nullable=True)

    phong_thi = relationship("PhongThi", back_populates="may_tram")
    thi_sinh_trong_phien = relationship("ThiSinhTrongPhien", back_populates="may_tram")


class PhienThi(Base):
    __tablename__ = "PhienThi"

    MaPhienThi = Column(Integer, primary_key=True, autoincrement=True)
    MaKyThi = Column(Integer, ForeignKey("KyThi.MaKyThi"), nullable=False)
    MaPhong = Column(Integer, ForeignKey("PhongThi.MaPhong"), nullable=False)
    MaCa = Column(Integer, ForeignKey("CaThi.MaCa"), nullable=False)
    TrangThai = Column(String(30), default="Chua bat dau", nullable=False)

    ky_thi = relationship("KyThi", back_populates="phien_thi")
    phong_thi = relationship("PhongThi", back_populates="phien_thi")
    ca_thi = relationship("CaThi", back_populates="phien_thi")
    thi_sinh = relationship("ThiSinhTrongPhien", back_populates="phien_thi")


class ThiSinhTrongPhien(Base):
    __tablename__ = "ThiSinhTrongPhien"

    MaThamGia = Column(Integer, primary_key=True, autoincrement=True)
    MaPhienThi = Column(Integer, ForeignKey("PhienThi.MaPhienThi"), nullable=False)
    MaSinhVien = Column(String(10), ForeignKey("SinhVien.MaSinhVien"), nullable=False)
    MaMay = Column(Integer, ForeignKey("MayTram.MaMay"), nullable=True)
    ThoiGianDangNhap = Column(DateTime, nullable=True)
    ThoiGianDangXuat = Column(DateTime, nullable=True)
    TrangThai = Column(String(30), default="Chua dang nhap", nullable=False)
    DoTuongDongXacThuc = Column(Numeric(6, 4), nullable=True)
    AnhXacThuc = Column(Unicode(500), nullable=True)

    phien_thi = relationship("PhienThi", back_populates="thi_sinh")
    sinh_vien = relationship("SinhVien", back_populates="danh_sach_tham_gia")
    may_tram = relationship("MayTram", back_populates="thi_sinh_trong_phien")
    cau_tra_loi = relationship("CauTraLoi", back_populates="thi_sinh")
    su_kien_canh_bao = relationship("SuKienCanhBao", back_populates="thi_sinh")


class CauHoi(Base):
    __tablename__ = "CauHoi"

    MaCauHoi = Column(Integer, primary_key=True, autoincrement=True)
    MaKyThi = Column(Integer, ForeignKey("KyThi.MaKyThi"), nullable=False)
    SoThuTu = Column(Integer, nullable=False)
    NoiDung = Column(String(1000), nullable=False)
    LuaChonA = Column(String(500), nullable=False)
    LuaChonB = Column(String(500), nullable=False)
    LuaChonC = Column(String(500), nullable=False)
    LuaChonD = Column(String(500), nullable=False)
    DapAnDung = Column(String(1), nullable=False)

    ky_thi = relationship("KyThi", back_populates="cau_hoi")
    cau_tra_loi = relationship("CauTraLoi", back_populates="cau_hoi")


class CauTraLoi(Base):
    __tablename__ = "CauTraLoi"

    MaCauTraLoi = Column(Integer, primary_key=True, autoincrement=True)
    MaThamGia = Column(Integer, ForeignKey("ThiSinhTrongPhien.MaThamGia"), nullable=False)
    MaCauHoi = Column(Integer, ForeignKey("CauHoi.MaCauHoi"), nullable=False)
    DapAnChon = Column(String(1), nullable=True)
    ThoiGianTraLoi = Column(DateTime, nullable=True)

    thi_sinh = relationship("ThiSinhTrongPhien", back_populates="cau_tra_loi")
    cau_hoi = relationship("CauHoi", back_populates="cau_tra_loi")


class SuKienCanhBao(Base):
    __tablename__ = "SuKienCanhBao"

    MaSuKien = Column(BigInteger, primary_key=True, autoincrement=True)
    MaThamGia = Column(Integer, ForeignKey("ThiSinhTrongPhien.MaThamGia"), nullable=False)
    LoaiSuKien = Column(Unicode(60), nullable=False)
    DoTuongDong = Column(Numeric(7, 5), nullable=True)
    SoKhuonMat = Column(Integer, default=0, nullable=False)
    ThoiGianBatDau = Column(DateTime, default=datetime.utcnow, nullable=False)
    ThoiGianKetThuc = Column(DateTime, nullable=True)
    ThoiLuongGiay = Column(Integer, nullable=True)
    DuongDanSnapshot = Column(Unicode(500), nullable=True)
    GhiChu = Column(Unicode(500), nullable=True)

    thi_sinh = relationship("ThiSinhTrongPhien", back_populates="su_kien_canh_bao")

