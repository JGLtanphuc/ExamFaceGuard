import base64
import json
import cv2
import numpy as np
from typing import Dict, Any, Optional, List

from deepface import DeepFace
from ..ai.retinaface import detect_faces
from ..ai.alignment import align_face
from ..ai.normalization import zscore_normalize
from ..ai.facenet import extract_embedding
from ..ai.similarity import cosine_similarity, verify_face


def decode_base64_image(base64_str: str) -> Optional[np.ndarray]:
    """Giải mã ảnh base64 từ camera browser gửi lên thành mảng numpy BGR"""
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]
        img_bytes = base64.b64decode(base64_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"[FaceService] Lỗi decode base64: {e}")
        return None


def parse_db_embedding(embedding_json_str: str) -> Optional[List[float]]:
    """Chuyển đổi chuỗi JSON FaceEmbedding trong database thành danh sách float"""
    try:
        if isinstance(embedding_json_str, list):
            return embedding_json_str
        return json.loads(embedding_json_str)
    except Exception as e:
        print(f"[FaceService] Lỗi parse embedding JSON: {e}")
        return None


def process_face_pipeline(
    img: np.ndarray,
    target_embedding: List[float],
    threshold: float = 0.70
) -> Dict[str, Any]:
    """
    Toàn bộ PIPELINE NHẬN DIỆN KHUÔN MẶT (RetinaFace + FaceNet512):
    Camera frame
    -> Tối ưu kích thước đầu vào (360px) giảm 50% tính toán ma trận ResNet-50 trên CPU
    -> RetinaFace phát hiện khuôn mặt & 5 Facial Landmarks
    -> Face Alignment căn chỉnh góc nghiêng
    -> Facenet Normalization
    -> FaceNet512 tạo embedding
    -> Cosine Similarity
    -> So sánh Ngưỡng Threshold (>= 70% là Đúng người)
    """
    if img is None or img.size == 0:
        return {
            "status": "LOI_CAMERA",
            "message": "Camera bị lỗi",
            "num_faces": 0,
            "similarity": 0.0,
            "bbox": None
        }

    # 1. Tối ưu kích thước frame đầu vào cho RetinaFace (Giảm tải tính toán ResNet-50 trên CPU)
    # Giới hạn chiều rộng tối đa 360px để tăng tốc độ nhận diện gấp đôi mà không giảm độ chính xác
    h_orig, w_orig = img.shape[:2]
    max_w = 360
    if w_orig > max_w:
        scale = max_w / float(w_orig)
        new_h = int(h_orig * scale)
        rf_img = cv2.resize(img, (max_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        scale = 1.0
        rf_img = img

    try:
        # Sử dụng đúng RetinaFace + FaceNet512 theo yêu cầu đề tài khóa luận
        reps = DeepFace.represent(
            img_path=rf_img,
            model_name="Facenet512",
            detector_backend="retinaface",
            enforce_detection=False
        )
    except Exception as e:
        print(f"[FaceService] Lỗi trích xuất nhận diện RetinaFace: {e}")
        return {
            "status": "KHONG_PHAT_HIEN_KHUON_MAT",
            "message": "Không phát hiện khuôn mặt",
            "num_faces": 0,
            "similarity": 0.0,
            "bbox": None
        }

    # Lọc các khuôn mặt hợp lệ có độ tin cậy face_confidence >= 0.50
    valid_faces = [r for r in reps if r.get("face_confidence", 0.0) >= 0.50]
    num_faces = len(valid_faces)

    if num_faces == 0:
        return {
            "status": "KHONG_PHAT_HIEN_KHUON_MAT",
            "message": "Không phát hiện khuôn mặt",
            "num_faces": 0,
            "similarity": 0.0,
            "bbox": None
        }

    if num_faces > 1:
        first_bbox = valid_faces[0].get("facial_area", {})
        x = int(first_bbox.get("x", 0) / scale)
        y = int(first_bbox.get("y", 0) / scale)
        w = int(first_bbox.get("w", 0) / scale)
        h = int(first_bbox.get("h", 0) / scale)
        return {
            "status": "PHAT_HIEN_NHIEU_KHUON_MAT",
            "message": f"Phát hiện {num_faces} khuôn mặt",
            "num_faces": num_faces,
            "similarity": 0.0,
            "bbox": [x, y, w, h]
        }

    # Đúng 1 khuôn mặt hợp lệ - nhân tỉ lệ ngược lại để khớp tọa độ ảnh gốc
    face = valid_faces[0]
    facial_area = face.get("facial_area", {})
    bbox = [
        int(facial_area.get("x", 0) / scale),
        int(facial_area.get("y", 0) / scale),
        int(facial_area.get("w", 0) / scale),
        int(facial_area.get("h", 0) / scale)
    ]
    extracted_vector = face.get("embedding", [])

    is_match, similarity = verify_face(extracted_vector, target_embedding, threshold=threshold)

    if is_match:
        return {
            "status": "DUNG_NGUOI",
            "message": "Đúng người",
            "num_faces": 1,
            "similarity": round(similarity, 4),
            "bbox": bbox
        }
    else:
        return {
            "status": "KHONG_DUNG_NGUOI",
            "message": "Không đúng người",
            "num_faces": 1,
            "similarity": round(similarity, 4),
            "bbox": bbox
        }

