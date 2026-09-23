import threading
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from ..database.models import MayTram, ThiSinhTrongPhien, PhongThi, PhienThi

# Lock tránh race condition khi 2 client cùng đăng nhập đồng thời
_machine_assignment_lock = threading.Lock()


def get_client_ip(request) -> Optional[str]:
    """
    Lấy IP client từ server-side request (ưu tiên CF-Connecting-IP, X-Forwarded-For khi qua Cloudflare/Proxy).
    """
    if not request:
        return None

    # 1. Nếu kết nối qua Cloudflare Tunnel / Reverse Proxy
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    if not request.client:
        return None
    ip = request.client.host
    # Chuẩn hóa localhost ipv6 ::1 về 127.0.0.1 để nhất quán
    if ip == "::1":
        ip = "127.0.0.1"
    return ip


def assign_machine_by_ip(
    db: Session,
    ma_sinh_vien: str,
    client_ip: str
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    CƠ CHẾ XÁC ĐỊNH MÁY TRẠM BẰNG IP (Bắt buộc):
    1. Xác định thí sinh trong phiên thi -> xác định MaPhienThi -> MaPhong của phòng thi.
    2. Kiểm tra nếu IP thuộc về phòng khác -> Từ chối.
    3. Nếu IP đã có trong phòng của phiên và chưa có ai dùng -> gán máy cho thí sinh.
    4. Nếu máy cũ đang bận (hoặc IP mới, hoặc nhiều thiết bị qua Cloudflare Tunnel / NAT) -> tự động cấp máy trống tiếp theo trong phòng.
    """
    if not client_ip:
        return False, "Không xác định được địa chỉ máy trạm.", None

    with _machine_assignment_lock:
        # Bước 1: Xác định thí sinh trong phiên thi
        ts = db.query(ThiSinhTrongPhien).filter(
            ThiSinhTrongPhien.MaSinhVien == ma_sinh_vien
        ).first()

        if not ts:
            return False, "Sinh viên chưa được phân bổ vào phiên thi nào.", None

        phien = db.query(PhienThi).filter(PhienThi.MaPhienThi == ts.MaPhienThi).first()
        if not phien:
            return False, "Không tìm thấy phiên thi tương ứng.", None

        ma_phong_chuan = phien.MaPhong
        phong = db.query(PhongThi).filter(PhongThi.MaPhong == ma_phong_chuan).first()
        ten_phong = phong.TenPhong if phong else f"Phòng {ma_phong_chuan}"

        # Bước 2: Kiểm tra nếu IP này đã được gán cố định cho một máy ở phòng KHÁC
        existing_other_room = db.query(MayTram).filter(
            MayTram.DiaChiIP == client_ip,
            MayTram.MaPhong != ma_phong_chuan
        ).first()

        if existing_other_room:
            other_room = db.query(PhongThi).filter(PhongThi.MaPhong == existing_other_room.MaPhong).first()
            other_room_name = other_room.TenPhong if other_room else "phòng khác"
            return False, (
                f"Máy trạm hiện tại không thuộc phòng thi được phân công "
                f"(IP đang gắn với {existing_other_room.TenMay} tại {other_room_name}, "
                f"trong khi ca thi của bạn diễn ra tại {ten_phong})."
            ), None

        # Bước 3: Tìm máy có IP trùng trong đúng phòng
        machine = db.query(MayTram).filter(
            MayTram.MaPhong == ma_phong_chuan,
            MayTram.DiaChiIP == client_ip
        ).first()

        if machine:
            # Kiểm tra xem máy này có đang được thí sinh KHÁC sử dụng trong cùng phiên không
            other_user = db.query(ThiSinhTrongPhien).filter(
                ThiSinhTrongPhien.MaPhienThi == ts.MaPhienThi,
                ThiSinhTrongPhien.MaMay == machine.MaMay,
                ThiSinhTrongPhien.MaSinhVien != ma_sinh_vien,
                ThiSinhTrongPhien.TrangThai.in_(["Dang thi", "Online"])
            ).first()

            # Nếu máy này chưa có ai dùng hoặc chính là máy cũ của thí sinh này -> Gán trực tiếp
            if not other_user:
                # Nếu thí sinh trước đó từng ở máy khác, giải phóng máy cũ
                if ts.MaMay and ts.MaMay != machine.MaMay:
                    old_m = db.query(MayTram).filter(MayTram.MaMay == ts.MaMay).first()
                    if old_m:
                        old_m.TrangThai = "Ngoai tuyen"

                machine.TrangThai = "Online"
                machine.LanCuoiKetNoi = datetime.utcnow()

                ts.MaMay = machine.MaMay
                ts.ThoiGianDangNhap = datetime.utcnow()
                ts.TrangThai = "Dang thi"

                db.commit()
                db.refresh(machine)
                db.refresh(ts)

                return True, "Xác định máy trạm thành công", {
                    "ma_may": machine.MaMay,
                    "ma_pc": machine.MaPC,
                    "ten_may": machine.TenMay,
                    "dia_chi_ip": machine.DiaChiIP,
                    "ten_phong": ten_phong
                }
            # Nếu máy này đang bận (ví dụ 2 thí sinh cùng test qua Cloudflare Tunnel / NAT chung IP), tự động nhảy xuống Bước 4 để cấp máy trống khác!

        # Bước 4: IP mới HOẶC máy trùng IP đang bận -> Cấp phát máy trống trong phòng
        # Lấy danh sách ID các máy đang bị chiếm bởi thí sinh khác trong ca này
        occupied_machine_ids = db.query(ThiSinhTrongPhien.MaMay).filter(
            ThiSinhTrongPhien.MaPhienThi == ts.MaPhienThi,
            ThiSinhTrongPhien.TrangThai.in_(["Dang thi", "Online"]),
            ThiSinhTrongPhien.MaSinhVien != ma_sinh_vien,
            ThiSinhTrongPhien.MaMay != None
        ).all()
        occupied_ids = [m[0] for m in occupied_machine_ids if m[0] is not None]

        # Ưu tiên 1: Máy chưa có IP
        free_machine = db.query(MayTram).filter(
            MayTram.MaPhong == ma_phong_chuan,
            or_(MayTram.DiaChiIP == None, MayTram.DiaChiIP == ""),
            ~MayTram.MaMay.in_(occupied_ids)
        ).order_by(MayTram.MaPC.asc()).first()

        # Ưu tiên 2: Nếu hết máy trống IP, lấy máy đang Ngoại tuyến chưa có thí sinh ngồi
        if not free_machine:
            free_machine = db.query(MayTram).filter(
                MayTram.MaPhong == ma_phong_chuan,
                ~MayTram.MaMay.in_(occupied_ids)
            ).order_by(MayTram.MaPC.asc()).first()

        if not free_machine:
            return False, f"Không còn máy trạm trống trong phòng thi {ten_phong}.", None

        # Gán IP và kích hoạt máy
        if ts.MaMay and ts.MaMay != free_machine.MaMay:
            old_m = db.query(MayTram).filter(MayTram.MaMay == ts.MaMay).first()
            if old_m:
                old_m.TrangThai = "Ngoai tuyen"

        free_machine.DiaChiIP = client_ip
        free_machine.TrangThai = "Online"
        free_machine.LanCuoiKetNoi = datetime.utcnow()

        ts.MaMay = free_machine.MaMay
        ts.ThoiGianDangNhap = datetime.utcnow()
        ts.TrangThai = "Dang thi"

        db.commit()
        db.refresh(free_machine)
        db.refresh(ts)

        return True, "Cấp phát máy trạm mới thành công", {
            "ma_may": free_machine.MaMay,
            "ma_pc": free_machine.MaPC,
            "ten_may": free_machine.TenMay,
            "dia_chi_ip": free_machine.DiaChiIP,
            "ten_phong": ten_phong
        }


def set_machine_offline(db: Session, ma_may: int):
    """Cập nhật trạng thái máy trạm về Ngoại tuyến khi thí sinh đăng xuất / mất kết nối"""
    machine = db.query(MayTram).filter(MayTram.MaMay == ma_may).first()
    if machine:
        machine.TrangThai = "Ngoai tuyen"
        machine.LanCuoiKetNoi = datetime.utcnow()
        db.commit()

