import os
import cv2
import numpy as np
from typing import Optional
from deepface import DeepFace

_arcface_model = None


def get_arcface_model():
    """Tải và cache mô hình ArcFace thông qua DeepFace"""
    global _arcface_model
    if _arcface_model is None:
        print("[ArcFace] Loading ArcFace model...")
        arcface_client = DeepFace.build_model("ArcFace")
        _arcface_model = arcface_client.model if hasattr(arcface_client, "model") else arcface_client
        print("[ArcFace] ArcFace model loaded successfully!")
    return _arcface_model


def extract_arcface_vector(face_crop: np.ndarray) -> Optional[np.ndarray]:
    """
    Trích xuất vector đặc trưng 512 chiều bằng ArcFace.
    Đầu vào: face_crop (numpy array BGR hoặc RGB)
    Đầu ra: numpy array 1D 512 chiều chuẩn hóa L2
    """
    if face_crop is None or face_crop.size == 0:
        return None

    model = get_arcface_model()
    if model is None:
        return None

    try:
        f112_arc = cv2.resize(face_crop, (112, 112))
        if f112_arc.dtype == np.uint8:
            val_arc = f112_arc.astype(np.float32)
        elif f112_arc.max() <= 1.0:
            val_arc = f112_arc * 255.0
        else:
            val_arc = f112_arc.astype(np.float32)

        b_arc = np.expand_dims(val_arc, axis=0).astype(np.float32)
        v3 = model.predict(b_arc, verbose=0)[0]
        v3 = np.array(v3, dtype=np.float32).flatten()

        norm = np.linalg.norm(v3)
        if norm > 0:
            v3 = v3 / norm
        return v3
    except Exception as e:
        print(f"[ArcFace] Lỗi trích xuất vector: {e}")
        return None
