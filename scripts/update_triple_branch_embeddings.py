import os
import sys
import json
import hashlib
import time
import cv2
import numpy as np
from datetime import datetime

# Đảm bảo import được module trong app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.database.connection import SessionLocal
from app.database.models import SinhVien
from deepface import DeepFace
from app.ai.facenet import extract_embedding
from app.ai.adaface import extract_adaface_vector, get_adaface_session
from app.ai.arcface import extract_arcface_vector, get_arcface_model


def extract_facenet_vector(face_crop: np.ndarray) -> np.ndarray:
    """Trích xuất vector 512 FaceNet512"""
    f160 = cv2.resize(face_crop, (160, 160))
    val1 = f160 * 255.0 if f160.max() <= 1.0 else f160.astype(np.float32)
    m1, s1 = val1.mean(), val1.std()
    s_adj1 = np.maximum(s1, 1.0 / np.sqrt(val1.size))
    std1 = (val1 - m1) / s_adj1
    b1 = np.expand_dims(std1, axis=0).astype(np.float32)
    return extract_embedding(b1)


def select_multi_centroids(vectors_list: list, max_c: int = 3) -> list:
    """Chọn tối đa max_c vector đa dạng nhất theo thuật toán kịch bản đề xuất"""
    if not vectors_list:
        return []
    if len(vectors_list) <= max_c:
        return [list(np.round(v, 6).astype(float)) for v in vectors_list]

    mean_vec = np.mean(vectors_list, axis=0)
    mean_vec = mean_vec / np.linalg.norm(mean_vec)
    selected = [mean_vec]
    remaining = list(vectors_list)
    while len(selected) < max_c and remaining:
        furthest = max(remaining, key=lambda v: min(1.0 - np.dot(v, s) for s in selected))
        selected.append(furthest)
        remaining.remove(furthest)
    return [list(np.round(v, 6).astype(float)) for v in selected]


def process_student_triple_branch(student_dir: str):
    """
    Trích xuất vector cả 3 nhánh (FaceNet512, AdaFace, ArcFace) cho sinh viên.
    """
    img_files = sorted([
        os.path.join(student_dir, f)
        for f in os.listdir(student_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])

    if not img_files:
        return None

    # Lọc ảnh trùng lặp
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

    v1_list = []
    v2_list = []
    v3_list = []

    for img_p in unique_images:
        try:
            data = np.fromfile(img_p, dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                continue

            h, w = img.shape[:2]
            max_w = 480
            if w > max_w:
                scale = max_w / float(w)
                scaled_img = cv2.resize(img, (max_w, int(h * scale)), interpolation=cv2.INTER_AREA)
            else:
                scaled_img = img

            faces = DeepFace.extract_faces(
                img_path=scaled_img,
                detector_backend="retinaface",
                enforce_detection=False,
                align=True
            )
            if not faces:
                continue

            fc = faces[0]["face"]

            v1 = extract_facenet_vector(fc)
            v2 = extract_adaface_vector(fc)
            v3 = extract_arcface_vector(fc)

            if v1 is not None and len(v1) == 512:
                v1_list.append(v1)
            if v2 is not None and len(v2) == 512:
                v2_list.append(v2)
            if v3 is not None and len(v3) == 512:
                v3_list.append(v3)

        except Exception as e:
            print(f"    [!] Lỗi xử lý ảnh {os.path.basename(img_p)}: {e}")
            continue

    if not v1_list:
        return None

    m1 = select_multi_centroids(v1_list, max_c=3)
    m2 = select_multi_centroids(v2_list, max_c=3)
    m3 = select_multi_centroids(v3_list, max_c=3)

    return {
        "facenet": m1,
        "adaface": m2,
        "arcface": m3
    }


def main():
    print("=" * 70)
    print("NÂNG CẤP VECTOR TRIPLE-BRANCH (FACENET512 + ADAFACE + ARCFACE)")
    print("ÁP DỤNG THUẬT TOÁN MULTI-CENTROIDS VÀ LƯU VÀO CƠ SỞ DỮ LIỆU")
    print("=" * 70)

    start_t = time.time()
    db = SessionLocal()

    try:
        # Khởi tạo trước cả 3 mô hình
        print("\n[1/3] Đang nạp trước 3 mô hình vào bộ nhớ...")
        DeepFace.build_model("Facenet512")
        get_adaface_session()
        get_arcface_model()
        print(" -> Đã sẵn sàng cả 3 mô hình!")

        # Quét 4 lớp
        print("\n[2/3] Quét danh sách 97 sinh viên và trích xuất vector 3 nhánh...")
        base_img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "IMG_DATA")

        student_list = []
        for cls_name in ["L01", "L03", "L04", "L05"]:
            cls_dir = os.path.join(base_img_dir, cls_name)
            if not os.path.isdir(cls_dir):
                continue
            for sf in sorted(os.listdir(cls_dir)):
                sp = os.path.join(cls_dir, sf)
                if not os.path.isdir(sp):
                    continue
                parts = sf.split("_", 1)
                mssv = parts[0].strip()
                student_list.append({
                    "class": cls_name,
                    "folder": sf,
                    "path": sp,
                    "mssv": mssv
                })

        print(f" -> Tìm thấy {len(student_list)} thư mục sinh viên.")

        # Lấy danh sách SinhVien từ DB sắp xếp theo STT
        db_students = db.query(SinhVien).order_by(SinhVien.STT.asc()).all()

        success_count = 0
        for idx, (stu_info, db_sv) in enumerate(zip(student_list, db_students), 1):
            t0 = time.time()
            folder_name = stu_info["folder"]
            print(f"[{idx:02d}/{len(student_list)}] {db_sv.MaSinhVien} | {db_sv.MSSV} | {db_sv.HoTen}...", end=" ", flush=True)

            triple_data = process_student_triple_branch(stu_info["path"])
            elap = time.time() - t0

            if triple_data:
                db_sv.FaceEmbedding = json.dumps(triple_data)
                db.commit()
                num_c1 = len(triple_data["facenet"])
                num_c2 = len(triple_data["adaface"])
                num_c3 = len(triple_data["arcface"])
                print(f"[OK] ({elap:.2f}s) -> Centroids: F:{num_c1}, Ad:{num_c2}, Ar:{num_c3}")
                success_count += 1
            else:
                print(f"[THẤT BẠI] ({elap:.2f}s)")

        total_time = time.time() - start_t
        print(f"\n[3/3] HOÀN TẤT: Cập nhật thành công {success_count}/{len(student_list)} sinh viên!")
        print(f"Tổng thời gian xử lý: {total_time:.2f}s ({total_time/60:.2f} phút).")

    except Exception as e:
        db.rollback()
        print(f"\n[!] Có lỗi xảy ra: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()

