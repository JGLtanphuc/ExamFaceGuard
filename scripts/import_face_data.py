import os
import sys
import re
import time
import json
import glob
import hashlib
import cv2
import numpy as np
from datetime import datetime

# Đảm bảo import được các module trong app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from app.database.connection import SessionLocal, engine
from app.database.models import (
    Base, TaiKhoan, SinhVien, PhongThi, CaThi, KyThi,
    MayTram, PhienThi, ThiSinhTrongPhien, CauHoi, CauTraLoi, SuKienCanhBao
)
from deepface import DeepFace


def format_student_name(raw_name: str) -> str:
    """
    Chuyển đổi chuỗi camelCase thành tên cách nhau bằng khoảng trắng.
    Ví dụ: 'PhungTanPhuc' -> 'Phung Tan Phuc'
           'PhạmMinhToan' -> 'Phạm Minh Toan'
    """
    # Tách trước các chữ cái in hoa nếu đứng sau chữ thường
    spaced = re.sub(
        r'([a-zđàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ])([A-ZĐÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ])',
        r'\1 \2',
        raw_name
    )
    return spaced.strip()


def extract_face_embedding(img_path: str, max_w: int = 640) -> np.ndarray:
    """
    Nhận diện khuôn mặt bằng RetinaFace và trích xuất vector 512 chiều bằng FaceNet512.
    Ảnh được resize về max_w (640px) để tối ưu hiệu năng tính toán trên CPU.
    Sử dụng np.fromfile và cv2.imdecode để hỗ trợ đường dẫn Unicode trên Windows.
    """
    try:
        data = np.fromfile(img_path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"    [!] Lỗi đọc file ảnh: {e}")
        return None

    if img is None or img.size == 0:
        return None

    h, w = img.shape[:2]
    if w > max_w:
        scale = max_w / float(w)
        scaled_img = cv2.resize(img, (max_w, int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        scaled_img = img

    try:
        # Gọi DeepFace với backend RetinaFace và model Facenet512
        reps = DeepFace.represent(
            img_path=scaled_img,
            model_name="Facenet512",
            detector_backend="retinaface",
            enforce_detection=False
        )
    except Exception as e:
        print(f"    [!] Lỗi DeepFace.represent: {e}")
        return None

    if not reps:
        return None

    # Lọc khuôn mặt có độ tin cậy >= 0.50 (hoặc chọn khuôn mặt có score cao nhất)
    valid_faces = [r for r in reps if r.get("face_confidence", 0.0) >= 0.50]
    best_face = valid_faces[0] if valid_faces else reps[0]

    emb = best_face.get("embedding", [])
    if not emb or len(emb) != 512:
        return None

    vec = np.array(emb, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def process_student_images(student_dir: str) -> list:
    """
    Xử lý tất cả ảnh trong thư mục sinh viên.
    Nếu có nhiều ảnh giống nhau, chỉ trích xuất một lần.
    Nếu có nhiều ảnh khác nhau, trích xuất tất cả và tính vector trung bình (centroid).
    """
    img_files = sorted([
        os.path.join(student_dir, f)
        for f in os.listdir(student_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])

    if not img_files:
        return None

    # Lọc ảnh trùng lặp theo mã băm MD5
    seen_hashes = set()
    unique_images = []
    for fpath in img_files:
        try:
            with open(fpath, "rb") as f:
                h = hashlib.md5(f.read()).hexdigest()
            if h not in seen_hashes:
                seen_hashes.add(h)
                unique_images.append(fpath)
        except Exception:
            unique_images.append(fpath)

    embeddings = []
    for img_path in unique_images:
        vec = extract_face_embedding(img_path)
        if vec is not None and len(vec) == 512:
            embeddings.append(vec)

    if not embeddings:
        return None

    # Lấy vector trung bình nếu có nhiều ảnh khác nhau
    avg_vec = np.mean(embeddings, axis=0)
    norm = np.linalg.norm(avg_vec)
    if norm > 0:
        avg_vec = avg_vec / norm

    # Làm tròn 6 chữ số thập phân cho chuỗi JSON
    return [round(float(x), 6) for x in avg_vec]


def main():
    print("=" * 65)
    print("HỆ THỐNG TRÍCH XUẤT FACE EMBEDDING (RETINA_FACE + FACENET512)")
    print("VÀ PHÂN BỔ DỮ LIỆU PHÒNG THI CA 1")
    print("=" * 65)

    start_total_time = time.time()
    db = SessionLocal()

    try:
        # 1. Khởi tạo mô hình Facenet512 và nạp trước vào cache
        print("\n[1/5] Đang nạp mô hình RetinaFace và FaceNet512 vào bộ nhớ...")
        t_model = time.time()
        DeepFace.build_model("Facenet512")
        print(f" -> Nạp mô hình hoàn tất trong {time.time() - t_model:.2f}s!")

        # 2. Chuẩn bị cấu trúc Phòng thi, Ca thi và Máy trạm
        print("\n[2/5] Chuẩn bị cấu trúc Phòng thi (PH01, PH03, PH04, PH05), Ca thi và Máy trạm...")

        # Bảo toàn Kỳ thi EX001
        ky_thi = db.query(KyThi).filter(KyThi.MaKyThiCode == "EX001").first()
        if not ky_thi:
            ky_thi = KyThi(
                MaKyThiCode="EX001",
                TenKyThi="Kỳ thi minh họa - Giám sát chống thi hộ",
                NgayThi=datetime.utcnow().date(),
                TrangThai="Dang dien ra",
                NguongNhanDien=0.7000,
                ThoiGianKhongCoMatGiay=3,
                SoLanSaiLienTiep=3,
                ThoiGianNhieuKhuonMatGiay=2
            )
            db.add(ky_thi)
            db.commit()
            db.refresh(ky_thi)

        # Bảo toàn Ca thi: Ca 1, Ca 2, Ca 3
        shifts_data = [
            ("Ca 1", "08:00:00", "09:00:00"),
            ("Ca 2", "09:15:00", "10:15:00"),
            ("Ca 3", "10:30:00", "11:30:00")
        ]
        ca_map = {}
        for ten_ca, gbd, gkt in shifts_data:
            ca = db.query(CaThi).filter(CaThi.TenCa == ten_ca).first()
            if not ca:
                ca = CaThi(TenCa=ten_ca, GioBatDau=gbd, GioKetThuc=gkt)
                db.add(ca)
                db.commit()
                db.refresh(ca)
            ca_map[ten_ca] = ca

        # Dọn dẹp dữ liệu con cũ để tránh xung đột Foreign Key
        print(" -> Dọn dẹp dữ liệu thi cũ (SuKienCanhBao, CauTraLoi, ThiSinhTrongPhien, SinhVien)...")
        db.query(SuKienCanhBao).delete()
        db.query(CauTraLoi).delete()
        db.query(ThiSinhTrongPhien).delete()
        db.query(SinhVien).delete()
        # Xóa tài khoản sinh viên cũ (giữ nguyên giamthi)
        db.query(TaiKhoan).filter(TaiKhoan.VaiTro == "SINH_VIEN").delete()
        db.commit()

        # Dọn dẹp PhienThi, MayTram và PhongThi cũ để tạo chuẩn PH01, PH03, PH04, PH05
        db.query(PhienThi).delete()
        db.query(MayTram).delete()
        db.query(PhongThi).delete()
        db.commit()

        # Tạo 4 phòng thi: PH01, PH03, PH04, PH05
        class_room_map = {
            "L01": "PH01",
            "L03": "PH03",
            "L04": "PH04",
            "L05": "PH05"
        }
        room_map = {}
        for cls_name, room_name in class_room_map.items():
            phong = PhongThi(
                TenPhong=room_name,
                SucChua=30,
                MoTa=f"Phòng thi {room_name} - Lớp {cls_name} (Tối đa 30 thí sinh)"
            )
            db.add(phong)
            db.commit()
            db.refresh(phong)
            room_map[cls_name] = phong

            # Tạo 30 máy trạm cho phòng (PC01 .. PC30)
            for pc_idx in range(1, 31):
                pc_code = f"PC{pc_idx:02d}"
                may = MayTram(
                    MaPhong=phong.MaPhong,
                    MaPC=pc_code,
                    TenMay=f"{room_name}-{pc_code}",
                    TrangThai="Ngoai tuyen"
                )
                db.add(may)
            db.commit()

        # Tạo Phiên thi cho tất cả các phòng và tất cả các ca (PH01-Ca1, PH01-Ca2, ...)
        # Điều này đảm bảo khi Giám thị chọn bất kỳ Ca nào trên dropdown đều có phiên thi hợp lệ
        phien_map = {}
        for cls_name, phong in room_map.items():
            for ten_ca, ca in ca_map.items():
                phien = PhienThi(
                    MaKyThi=ky_thi.MaKyThi,
                    MaPhong=phong.MaPhong,
                    MaCa=ca.MaCa,
                    TrangThai="Chua bat dau"
                )
                db.add(phien)
                db.commit()
                db.refresh(phien)
                phien_map[(cls_name, ten_ca)] = phien

        print(f" -> Đã tạo 4 phòng thi ({list(class_room_map.values())}), 120 máy trạm và 12 phiên thi!")

        # 3. Quét danh sách sinh viên trong thư mục IMG_DATA
        print("\n[3/5] Quét danh sách sinh viên trong IMG_DATA...")
        base_img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "IMG_DATA")

        student_records = []
        for cls_name in ["L01", "L03", "L04", "L05"]:
            cls_dir = os.path.join(base_img_dir, cls_name)
            if not os.path.isdir(cls_dir):
                print(f" [!] Thư mục lớp {cls_name} không tồn tại: {cls_dir}")
                continue

            stu_folders = sorted(os.listdir(cls_dir))
            for sf in stu_folders:
                stu_path = os.path.join(cls_dir, sf)
                if not os.path.isdir(stu_path):
                    continue

                parts = sf.split("_", 1)
                mssv = parts[0].strip()
                raw_name = parts[1].strip() if len(parts) > 1 else ""

                # Sửa MSSV đúng của Trương Lê Hải Quân (2001230731) nếu bị gõ nhầm 2001230695 trong thư mục
                if "TruongLeHaiQuan" in raw_name and mssv == "2001230695":
                    mssv = "2001230731"

                ho_ten = format_student_name(raw_name)
                student_records.append({
                    "class_name": cls_name,
                    "folder_name": sf,
                    "folder_path": stu_path,
                    "mssv": mssv,
                    "ho_ten": ho_ten
                })

        print(f" -> Tìm thấy tổng cộng {len(student_records)} sinh viên trên cả 4 lớp.")

        # 4. Trích xuất Face Embedding và nạp vào CSDL
        print("\n[4/5] Tiến hành trích xuất vector 512 chiều bằng RetinaFace + FaceNet512...")
        ca1 = ca_map["Ca 1"]

        success_count = 0
        fail_count = 0

        for idx, stu in enumerate(student_records, 1):
            stt = idx
            ma_sinh_vien = f"SV{stt:03d}"
            ten_dang_nhap = f"sv{stt:03d}"
            cls_name = stu["class_name"]
            mssv = stu["mssv"]
            ho_ten = stu["ho_ten"]
            folder_path = stu["folder_path"]

            t0 = time.time()
            print(f"[{stt:02d}/{len(student_records)}] {cls_name} | {ma_sinh_vien} | {mssv} | {ho_ten}...", end=" ", flush=True)

            embedding_vector = process_student_images(folder_path)
            elap = time.time() - t0

            if embedding_vector is None:
                print(f"[THẤT BẠI] ({elap:.2f}s) - Không nhận diện được khuôn mặt!")
                fail_count += 1
                # Nếu không nhận diện được (rất hiếm), tạo vector 512 zeros chuẩn để không gãy DB
                embedding_vector = [0.0] * 512
            else:
                print(f"[THÀNH CÔNG] ({elap:.2f}s)")
                success_count += 1

            embedding_json = json.dumps(embedding_vector)

            # 4.1. Tạo Tài khoản cho sinh viên (Đăng nhập được bằng svXXX hoặc MSSV)
            tk = TaiKhoan(
                TenDangNhap=ten_dang_nhap,
                MatKhau="123456",
                VaiTro="SINH_VIEN",
                DangHoatDong=True
            )
            db.add(tk)
            db.commit()
            db.refresh(tk)

            # 4.2. Tạo Sinh viên
            sv = SinhVien(
                MaSinhVien=ma_sinh_vien,
                STT=stt,
                MSSV=mssv,
                HoTen=ho_ten,
                MaTaiKhoan=tk.MaTaiKhoan,
                FaceEmbedding=embedding_json
            )
            db.add(sv)
            db.commit()

            # 4.3. Xếp vào phòng thi tương ứng trong Ca 1
            phien_thi_ca1 = phien_map[(cls_name, "Ca 1")]
            ts = ThiSinhTrongPhien(
                MaPhienThi=phien_thi_ca1.MaPhienThi,
                MaSinhVien=ma_sinh_vien,
                TrangThai="Chua dang nhap"
            )
            db.add(ts)
            db.commit()

        # 5. Tổng kết và kiểm tra
        print("\n[5/5] Kiểm tra tổng kết cơ sở dữ liệu sau khi nạp:")
        print(f" -> Thành công: {success_count}/{len(student_records)} sinh viên")
        if fail_count > 0:
            print(f" -> Cần lưu ý: {fail_count} sinh viên chưa trích xuất được vector.")

        # Thống kê phân bổ theo phòng và ca
        print("\nBảng phân bổ thí sinh theo Phòng thi & Ca thi:")
        print("-" * 55)
        print(f"{'Phòng':<10} {'Ca thi':<10} {'Lớp':<10} {'Số thí sinh':<15}")
        print("-" * 55)
        for cls_name, room_name in class_room_map.items():
            for ten_ca in ["Ca 1", "Ca 2", "Ca 3"]:
                phien = phien_map[(cls_name, ten_ca)]
                count = db.query(ThiSinhTrongPhien).filter(ThiSinhTrongPhien.MaPhienThi == phien.MaPhienThi).count()
                print(f"{room_name:<10} {ten_ca:<10} {cls_name:<10} {count:<15}")
        print("-" * 55)

        total_time = time.time() - start_total_time
        print(f"\n=> TOÀN BỘ TIẾN TRÌNH HOÀN THÀNH XUẤT SẮC TRONG {total_time:.2f} GIÂY ({total_time/60:.2f} PHÚT)!")

    except Exception as e:
        db.rollback()
        print(f"\n[!] Có lỗi xảy ra trong quá trình thực hiện: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
