import cv2
import numpy as np
from typing import List, Dict, Any
from retinaface import RetinaFace


def detect_faces(img: np.ndarray) -> List[Dict[str, Any]]:
    """
    Sử dụng RetinaFace để phát hiện các khuôn mặt trong ảnh BGR.
    Trả về danh sách các khuôn mặt, mỗi khuôn mặt gồm:
    - facial_area: [x, y, w, h]
    - score: độ tin cậy
    - landmarks: {left_eye, right_eye, nose, mouth_left, mouth_right}
    """
    if img is None or img.size == 0:
        return []

    try:
        raw_faces = RetinaFace.detect_faces(img)
    except Exception as e:
        print(f"[RetinaFace] Lỗi phát hiện: {e}")
        return []

    if not isinstance(raw_faces, dict):
        return []

    results = []
    for key, face_data in raw_faces.items():
        area = face_data.get("facial_area", [])
        score = face_data.get("score", 0.0)
        landmarks = face_data.get("landmarks", {})

        # facial_area dạng [x1, y1, x2, y2]
        if len(area) == 4:
            x1, y1, x2, y2 = area
            w = max(0, x2 - x1)
            h = max(0, y2 - y1)
            bbox = [int(x1), int(y1), int(w), int(h)]
        else:
            bbox = [0, 0, img.shape[1], img.shape[0]]

        results.append({
            "key": key,
            "bbox": bbox,  # [x, y, w, h]
            "score": float(score),
            "landmarks": landmarks
        })

    return results

