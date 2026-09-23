import cv2
import numpy as np
from typing import Dict, Tuple, Optional


def align_face(
    img: np.ndarray,
    landmarks: Dict[str, Tuple[float, float]],
    target_size: Tuple[int, int] = (160, 160)
) -> np.ndarray:
    """
    Căn chỉnh khuôn mặt (Face Alignment) dựa trên 5 Facial Landmarks (đặc biệt là 2 mắt).
    - Tính góc nghiêng giữa 2 mắt
    - Xoay ảnh quanh trung điểm giữa 2 mắt để đường nối 2 mắt nằm ngang
    - Cắt và resize khuôn mặt về kích thước chuẩn (160x160) cho FaceNet512
    """
    if img is None or img.size == 0:
        return np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)

    left_eye = landmarks.get("left_eye")
    right_eye = landmarks.get("right_eye")

    if not left_eye or not right_eye:
        # Nếu không có toạ độ mắt, resize ảnh gốc về target_size
        return cv2.resize(img, target_size)

    left_eye = np.array(left_eye, dtype=np.float32)
    right_eye = np.array(right_eye, dtype=np.float32)

    # Tính độ chênh lệch giữa hai mắt
    dY = right_eye[1] - left_eye[1]
    dX = right_eye[0] - left_eye[0]
    angle = np.degrees(np.arctan2(dY, dX))

    # Điểm trung tâm giữa 2 mắt
    eyes_center = ((left_eye[0] + right_eye[0]) / 2.0, (left_eye[1] + right_eye[1]) / 2.0)

    # Tính khoảng cách giữa hai mắt
    dist = np.sqrt((dX ** 2) + (dY ** 2))
    desired_dist = target_size[0] * 0.35
    scale = desired_dist / max(dist, 1e-5)

    # Ma trận xoay 2D
    M = cv2.getRotationMatrix2D(eyes_center, angle, scale)

    # Căn chỉnh sao cho mắt nằm ở vị trí mong muốn trong khung hình (khoảng 35% từ trên xuống)
    tX = target_size[0] * 0.5
    tY = target_size[1] * 0.38
    M[0, 2] += (tX - eyes_center[0])
    M[1, 2] += (tY - eyes_center[1])

    # Thực hiện Warp Affine
    aligned = cv2.warpAffine(
        img,
        M,
        (target_size[0], target_size[1]),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )

    return aligned

