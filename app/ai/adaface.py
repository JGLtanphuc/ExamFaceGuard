import os
import cv2
import numpy as np
from typing import Optional
import onnxruntime as ort

_adaface_session = None

WEIGHTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "weights")
WEIGHTS_PATH = os.path.join(WEIGHTS_DIR, "adaface_ir_18.onnx")


def get_adaface_session() -> Optional[ort.InferenceSession]:
    """Tải và cache phiên suy luận ONNX Runtime cho AdaFace IR-18"""
    global _adaface_session
    if _adaface_session is None:
        if not os.path.exists(WEIGHTS_PATH):
            print(f"[AdaFace] CẢNH BÁO: Không tìm thấy file trọng số tại {WEIGHTS_PATH}")
            return None
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        print("[AdaFace] Loading AdaFace IR-18 (ONNX) model...")
        _adaface_session = ort.InferenceSession(WEIGHTS_PATH, options, providers=["CPUExecutionProvider"])
        print("[AdaFace] AdaFace IR-18 model loaded successfully!")
    return _adaface_session


def extract_adaface_vector(face_crop: np.ndarray) -> Optional[np.ndarray]:
    """
    Trích xuất vector đặc trưng 512 chiều bằng AdaFace IR-18 (ONNX).
    Đầu vào: face_crop (numpy array BGR hoặc RGB)
    Đầu ra: numpy array 1D 512 chiều chuẩn hóa L2
    """
    if face_crop is None or face_crop.size == 0:
        return None

    session = get_adaface_session()
    if session is None:
        return None

    try:
        f112_ada = cv2.resize(face_crop, (112, 112))
        if face_crop.dtype == np.uint8:
            u112 = f112_ada
        elif f112_ada.max() <= 1.0:
            u112 = (f112_ada * 255.0).astype(np.uint8)
        else:
            u112 = f112_ada.astype(np.uint8)

        norm_ada = (u112.astype(np.float32) - 127.5) / 128.0
        trans_ada = np.transpose(norm_ada, (2, 0, 1))
        b_ada = np.expand_dims(trans_ada, axis=0).astype(np.float32)

        in_name = session.get_inputs()[0].name
        out_name = session.get_outputs()[0].name
        outs = session.run([out_name], {in_name: b_ada})
        v2 = outs[0].flatten().astype(np.float32)

        norm = np.linalg.norm(v2)
        if norm > 0:
            v2 = v2 / norm
        return v2
    except Exception as e:
        print(f"[AdaFace] Lỗi trích xuất vector: {e}")
        return None
