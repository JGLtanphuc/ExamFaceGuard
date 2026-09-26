import sys
import os
import cv2
import json
import numpy as np

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
from app.services.face_service import process_face_pipeline, parse_db_embedding

def test_pipeline_on_db():
    db = SessionLocal()
    try:
        sv = db.query(SinhVien).filter(SinhVien.MaSinhVien == 'SV001').first()
        if not sv:
            print("Khong tim thay SV001")
            return
        
        print(f"Kiem tra: {sv.MaSinhVien} ({sv.MSSV}) - {sv.HoTen}")
        emb_data = parse_db_embedding(sv.FaceEmbedding)
        print(f"So luong centroids: FaceNet={len(emb_data['facenet'])}, AdaFace={len(emb_data['adaface'])}, ArcFace={len(emb_data['arcface'])}")

        # Lấy 1 ảnh thực tế của SV001
        img_folder = "IMG_DATA/L01/2001230695_PhungTanPhuc"
        if os.path.exists(img_folder):
            files = [f for f in os.listdir(img_folder) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
            if files:
                test_img_path = os.path.join(img_folder, files[0])
                print(f"\n--- TEST 1: ANH CHINH CHU ({test_img_path}) ---")
                img_data = np.fromfile(test_img_path, dtype=np.uint8)
                img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)

                res = process_face_pipeline(img, emb_data)
                print(f"Status: {res['status']}")
                print(f"Method: {res.get('method')}")
                print(f"Distance: {res.get('distance')}")
                print(f"Similarity: {res.get('similarity')}")
                print(f"Message: {res.get('message')}")

        # Lấy 1 ảnh của người khác
        other_folder = "IMG_DATA/L01/2045240004_TangTruongAn"
        if os.path.exists(other_folder):
            files2 = [f for f in os.listdir(other_folder) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
            if files2:
                other_img_path = os.path.join(other_folder, files2[0])
                print(f"\n--- TEST 2: ANH NGUOI KHAC / THI HO ({other_img_path}) ---")
                img_data2 = np.fromfile(other_img_path, dtype=np.uint8)
                img2 = cv2.imdecode(img_data2, cv2.IMREAD_COLOR)

                res2 = process_face_pipeline(img2, emb_data)
                print(f"Status: {res2['status']}")
                print(f"Method: {res2.get('method')}")
                print(f"Distance: {res2.get('distance')}")
                print(f"Similarity: {res2.get('similarity')}")
                print(f"Message: {res2.get('message')}")

    finally:
        db.close()

if __name__ == "__main__":
    test_pipeline_on_db()
