import numpy as np
from typing import Optional
from deepface import DeepFace

# Khởi tạo model cache để không load lại nhiều lần
_facenet512_model = None


def get_facenet512_model():
    """Tải và cache mô hình Facenet512"""
    global _facenet512_model
    if _facenet512_model is None:
        print("[AI] Loading FaceNet512 model into memory...")
        _facenet512_model = DeepFace.build_model("Facenet512")
        print("[AI] FaceNet512 model loaded successfully!")
    return _facenet512_model


def extract_embedding(preprocessed_face: np.ndarray) -> np.ndarray:
    """
    Nhận diện và trích xuất vector đặc trưng 512 chiều từ ảnh khuôn mặt đã qua căn chỉnh và chuẩn hóa.
    Đầu vào: ảnh shape (160, 160, 3) dạng float32
    Đầu ra: numpy array 1D 512 chiều chuẩn hóa L2
    """
    client = get_facenet512_model()

    # Trích xuất vector đặc trưng tùy theo kiểu đối tượng DeepFace model
    if hasattr(client, "forward"):
        if len(preprocessed_face.shape) == 3:
            raw_embedding = client.forward(preprocessed_face)
        else:
            raw_embedding = client.forward(preprocessed_face[0])
    elif hasattr(client, "model"):
        input_tensor = np.expand_dims(preprocessed_face, axis=0) if len(preprocessed_face.shape) == 3 else preprocessed_face
        raw_embedding = client.model.predict(input_tensor, verbose=0)
    elif hasattr(client, "predict"):
        input_tensor = np.expand_dims(preprocessed_face, axis=0) if len(preprocessed_face.shape) == 3 else preprocessed_face
        raw_embedding = client.predict(input_tensor, verbose=0)
    else:
        raise RuntimeError(f"Unknown Facenet model client type: {type(client)}")

    embedding = np.array(raw_embedding, dtype=np.float32).flatten()

    # Chuẩn hóa L2 vector
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    return embedding

