import numpy as np


def zscore_normalize(image: np.ndarray) -> np.ndarray:
    """
    Chuẩn hóa Z-Score (Z-Score Normalization / Whitening) cho ảnh khuôn mặt:
    x_norm = (x - mean) / max(std, 1.0 / sqrt(N))
    Đưa phân phối giá trị pixel về mean ~ 0, std ~ 1.
    """
    img_float = image.astype(np.float32)
    mean = np.mean(img_float)
    std = np.std(img_float)
    std_adj = np.maximum(std, 1.0 / np.sqrt(img_float.size))
    normalized = (img_float - mean) / std_adj
    return normalized

