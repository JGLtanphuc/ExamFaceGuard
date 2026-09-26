import os
import time
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional

from .face_service import decode_base64_image, parse_db_embedding, process_face_pipeline


CAPTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)


def verify_checkin_face(
    image_base64: str,
    ma_sinh_vien: str,
    target_embedding_str: str,
    threshold: float = 0.70
) -> Dict[str, Any]:
    """
    Xác thực khuôn mặt thí sinh tại bước Đăng nhập (Check-in Verification) bằng RetinaFace + FaceNet512:
    1. Giải mã ảnh Base64 từ Camera.
    2. Lưu file ảnh snapshot vào app/static/captures/ để Giám thị đối sánh.
    3. Chạy pipeline RetinaFace + FaceNet512 + Cosine Similarity.
    4. Trả về kết quả đánh giá (Đúng người / Không đúng người / Không có mặt / Nhiều mặt).
    """
    if not image_base64 or not image_base64.strip():
        return {
            "success": False,
            "status": "LOI_HINH_ANH",
            "message": "Không nhận được hình ảnh từ camera. Vui lòng thử lại.",
            "similarity": 0.0,
            "num_faces": 0,
            "image_path": None
        }

    img = decode_base64_image(image_base64)
    if img is None or img.size == 0:
        return {
            "success": False,
            "status": "LOI_HINH_ANH",
            "message": "Không thể giải mã hình ảnh từ camera. Vui lòng chụp lại.",
            "similarity": 0.0,
            "num_faces": 0,
            "image_path": None
        }

    # Lưu ảnh snapshot vào đĩa
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"verify_{ma_sinh_vien}_{timestamp_str}.jpg"
    abs_file_path = os.path.join(CAPTURES_DIR, file_name)
    web_file_path = f"/static/captures/{file_name}"

    try:
        cv2.imwrite(abs_file_path, img)
    except Exception as e:
        print(f"[VerificationService] Lưu ảnh snapshot thất bại: {e}")
        web_file_path = None

    # Parse FaceEmbedding của sinh viên
    target_embedding = parse_db_embedding(target_embedding_str)
    if not target_embedding:
        return {
            "success": False,
            "status": "LOI_DATABASE",
            "message": "Hồ sơ thí sinh chưa có FaceEmbedding khuôn mặt chuẩn trong CSDL.",
            "similarity": 0.0,
            "num_faces": 0,
            "image_path": web_file_path
        }

    # Chạy quy trình nhận diện khuôn mặt
    pipeline_result = process_face_pipeline(img, target_embedding, threshold=threshold)
    status = pipeline_result.get("status")
    similarity = pipeline_result.get("similarity", 0.0)
    num_faces = pipeline_result.get("num_faces", 0)
    method = pipeline_result.get("method", "SINGLE_MODEL")
    pipe_msg = pipeline_result.get("message")

    if status == "DUNG_NGUOI":
        pct = round(similarity * 100, 1)
        msg = pipe_msg or f"Xác thực thành công! Khuôn mặt trùng khớp hồ sơ ({pct}%). Đang chuyển vào phòng thi..."
        return {
            "success": True,
            "status": "DUNG_NGUOI",
            "message": msg,
            "similarity": similarity,
            "method": method,
            "num_faces": 1,
            "image_path": web_file_path
        }
    elif status == "KHONG_DUNG_NGUOI":
        pct = round(similarity * 100, 1)
        msg = pipe_msg or f"Xác thực thất bại! Khuôn mặt không khớp với hồ sơ thí sinh. Độ tương đồng {pct}%."
        return {
            "success": False,
            "status": "KHONG_DUNG_NGUOI",
            "message": msg,
            "similarity": similarity,
            "method": method,
            "num_faces": 1,
            "image_path": web_file_path
        }
    elif status == "KHONG_PHAT_HIEN_KHUON_MAT":
        return {
            "success": False,
            "status": "KHONG_PHAT_HIEN_KHUON_MAT",
            "message": "Không phát hiện khuôn mặt trong ảnh. Vui lòng nhìn thẳng vào camera, đủ ánh sáng và chụp lại.",
            "similarity": 0.0,
            "num_faces": 0,
            "image_path": web_file_path
        }
    elif status == "PHAT_HIEN_NHIEU_KHUON_MAT":
        return {
            "success": False,
            "status": "PHAT_HIEN_NHIEU_KHUON_MAT",
            "message": f"Phát hiện {num_faces} khuôn mặt trong khung hình. Chỉ cho phép duy nhất thí sinh dự thi xuất hiện.",
            "similarity": 0.0,
            "num_faces": num_faces,
            "image_path": web_file_path
        }
    else:
        return {
            "success": False,
            "status": status or "LOI_HE_THONG",
            "message": pipeline_result.get("message", "Lỗi trong quá trình đối sánh khuôn mặt. Vui lòng thử lại."),
            "similarity": similarity,
            "num_faces": num_faces,
            "image_path": web_file_path
        }

