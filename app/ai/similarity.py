import numpy as np
from typing import Tuple, Union, List


def cosine_similarity(vec1: Union[np.ndarray, List[float]], vec2: Union[np.ndarray, List[float]]) -> float:
    """
    Tính độ tương đồng Cosine giữa 2 vector embedding:
    similarity = (u . v) / (||u|| * ||v||)
    Trả về giá trị từ -1.0 đến 1.0 (với FaceNet chuẩn hóa thường từ 0.0 đến 1.0)
    """
    u = np.array(vec1, dtype=np.float32).flatten()
    v = np.array(vec2, dtype=np.float32).flatten()

    norm_u = np.linalg.norm(u)
    norm_v = np.linalg.norm(v)

    if norm_u == 0 or norm_v == 0:
        return 0.0

    dot_product = np.dot(u, v)
    sim = dot_product / (norm_u * norm_v)
    return float(np.clip(sim, -1.0, 1.0))


def cosine_distance(vec1: Union[np.ndarray, List[float]], vec2: Union[np.ndarray, List[float]]) -> float:
    """
    Tính khoảng cách Cosine (Cosine Distance D):
    D = 1.0 - Cosine Similarity
    Theo quy tắc slide nghiên cứu: D < tau => Chấp nhận (Match).
    """
    sim = cosine_similarity(vec1, vec2)
    return float(np.clip(1.0 - sim, 0.0, 2.0))


def verify_face(
    embedding: Union[np.ndarray, List[float]],
    target_embedding: Union[np.ndarray, List[float]],
    threshold: float = 0.70
) -> Tuple[bool, float]:
    """
    So sánh vector đặc trưng hiện tại với vector tâm cụm Centroid lưu trong CSDL:
    - Độ tương đồng Cosine: sim >= threshold (ví dụ: 0.70)
    - Tương đương Khoảng cách Cosine: D < tau (với tau = 1.0 - threshold = 0.30)
    Trả về: (is_match, similarity)
    """
    sim = cosine_similarity(embedding, target_embedding)
    is_match = sim >= threshold
    return is_match, sim

