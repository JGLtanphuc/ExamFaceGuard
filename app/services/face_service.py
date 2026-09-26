import base64
import json
import cv2
import numpy as np
from typing import Dict, Any, Optional, List, Tuple

from deepface import DeepFace
from ..ai.facenet import extract_embedding
from ..ai.adaface import extract_adaface_vector
from ..ai.arcface import extract_arcface_vector


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


def parse_db_embedding(embedding_json_str: str) -> Dict[str, List[np.ndarray]]:
    """
    Chuyển đổi chuỗi JSON FaceEmbedding trong database thành từ điển các centroid vector:
    Hỗ trợ 2 định dạng:
    1. Cấu trúc mới Multi-Branch Triple Fusion:
       {"facenet": [[...], ...], "adaface": [[...], ...], "arcface": [[...], ...]}
    2. Cấu trúc cũ mảng 1D: [f1, f2, ..., f512]
    """
    result = {"facenet": [], "adaface": [], "arcface": []}
    if not embedding_json_str:
        return result

    try:
        data = embedding_json_str if not isinstance(embedding_json_str, str) else json.loads(embedding_json_str)

        if isinstance(data, dict):
            for branch in ["facenet", "adaface", "arcface"]:
                vecs = data.get(branch) or data.get(branch[0], [])
                if isinstance(vecs, list):
                    for v in vecs:
                        if isinstance(v, list) and len(v) == 512:
                            arr = np.array(v, dtype=np.float32)
                            norm = np.linalg.norm(arr)
                            if norm > 0:
                                arr = arr / norm
                            result[branch].append(arr)
        elif isinstance(data, list):
            # Tương thích ngược: nếu chỉ có 1 mảng 512 float
            if len(data) == 512 and isinstance(data[0], (int, float)):
                arr = np.array(data, dtype=np.float32)
                norm = np.linalg.norm(arr)
                if norm > 0:
                    arr = arr / norm
                result["facenet"].append(arr)
            elif len(data) > 0 and isinstance(data[0], list):
                for v in data:
                    arr = np.array(v, dtype=np.float32)
                    norm = np.linalg.norm(arr)
                    if norm > 0:
                        arr = arr / norm
                    result["facenet"].append(arr)
    except Exception as e:
        print(f"[FaceService] Lỗi parse embedding JSON: {e}")

    return result


def extract_facenet_vector(face_crop: np.ndarray) -> Optional[np.ndarray]:
    """Trích xuất vector 512 từ crop khuôn mặt theo chuẩn Z-Score Whitening của FaceNet512"""
    try:
        f160 = cv2.resize(face_crop, (160, 160))
        val1 = f160 * 255.0 if f160.max() <= 1.0 else f160.astype(np.float32)
        m1, s1 = val1.mean(), val1.std()
        s_adj1 = np.maximum(s1, 1.0 / np.sqrt(val1.size))
        std1 = (val1 - m1) / s_adj1
        b1 = np.expand_dims(std1, axis=0).astype(np.float32)
        return extract_embedding(b1)
    except Exception as e:
        print(f"[FaceService] Lỗi trích xuất FaceNet512: {e}")
        return None


def process_face_pipeline(
    img: np.ndarray,
    target_embedding_data: Any,
    threshold: float = 0.70
) -> Dict[str, Any]:
    """
    PIPELINE NÂNG CẤP: EARLY EXIT TRIPLE-BRANCH FUSION
    Kiến trúc: RetinaFace (Phát hiện & Căn chỉnh) + Thực thi có điều kiện (Lazy Evaluation)
    Tác giả đề xuất: Trương Lê Hải Quân

    Quy trình:
    1. RetinaFace phát hiện khuôn mặt & căn chỉnh (Alignment)
    2. Nhánh 1 (FaceNet512) trích xuất đặc trưng & tính khoảng cách Cosine d1:
       - Nếu d1 <= 0.31 (Rất giống): EARLY EXIT -> PASS ngay lập tức, tiết kiệm 70% CPU.
       - Nếu d1 >= 0.42 (Rất khác): EARLY EXIT -> FAIL ngay lập tức.
       - Nếu 0.31 < d1 < 0.42 (Vùng ranh giới Gray Zone):
         Kích hoạt Hội chẩn: Nhánh 2 (AdaFace ONNX) + Nhánh 3 (ArcFace)
         fusion_score = 0.5 * d1 + 0.25 * d2 + 0.25 * d3
         Nếu fusion_score <= 0.36 -> PASS, ngược lại FAIL.
    """
    if img is None or img.size == 0:
        return {
            "status": "LOI_CAMERA",
            "message": "Camera bị lỗi",
            "num_faces": 0,
            "similarity": 0.0,
            "method": "ERROR",
            "bbox": None
        }

    # 1. Tối ưu kích thước đầu vào (chiều rộng tối đa 480px) để RetinaFace xử lý nhanh trên CPU
    h_orig, w_orig = img.shape[:2]
    max_w = 480
    if w_orig > max_w:
        scale = max_w / float(w_orig)
        new_h = int(h_orig * scale)
        rf_img = cv2.resize(img, (max_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        scale = 1.0
        rf_img = img

    try:
        # RetinaFace phát hiện & căn chỉnh (align=True)
        faces = DeepFace.extract_faces(
            img_path=rf_img,
            detector_backend="retinaface",
            enforce_detection=False,
            align=True
        )
    except Exception as e:
        print(f"[FaceService] Lỗi trích xuất nhận diện RetinaFace: {e}")
        return {
            "status": "KHONG_PHAT_HIEN_KHUON_MAT",
            "message": "Không phát hiện khuôn mặt",
            "num_faces": 0,
            "similarity": 0.0,
            "method": "RETINAFACE_FAILED",
            "bbox": None
        }

    # Lọc các khuôn mặt hợp lệ có confidence >= 0.50
    valid_faces = [r for r in faces if r.get("confidence", 0.0) >= 0.50]
    num_faces = len(valid_faces)

    if num_faces == 0:
        return {
            "status": "KHONG_PHAT_HIEN_KHUON_MAT",
            "message": "Không phát hiện khuôn mặt trong khung hình",
            "num_faces": 0,
            "similarity": 0.0,
            "method": "NO_FACE",
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
            "message": f"Phát hiện {num_faces} khuôn mặt. Chỉ cho phép duy nhất thí sinh.",
            "num_faces": num_faces,
            "similarity": 0.0,
            "method": "MULTI_FACES",
            "bbox": [x, y, w, h]
        }

    # Lấy khuôn mặt duy nhất hợp lệ
    face_data = valid_faces[0]
    facial_area = face_data.get("facial_area", {})
    bbox = [
        int(facial_area.get("x", 0) / scale),
        int(facial_area.get("y", 0) / scale),
        int(facial_area.get("w", 0) / scale),
        int(facial_area.get("h", 0) / scale)
    ]
    face_crop = face_data.get("face")

    # Chuẩn bị dữ liệu đặc trưng mục tiêu (target)
    if isinstance(target_embedding_data, str):
        target_dict = parse_db_embedding(target_embedding_data)
    elif isinstance(target_embedding_data, dict):
        target_dict = target_embedding_data
    else:
        target_dict = parse_db_embedding(json.dumps(target_embedding_data))

    target_m1 = target_dict.get("facenet", [])
    target_m2 = target_dict.get("adaface", [])
    target_m3 = target_dict.get("arcface", [])

    if not target_m1:
        return {
            "status": "LOI_DATABASE",
            "message": "Hồ sơ thí sinh chưa có vector khuôn mặt mẫu trong CSDL.",
            "num_faces": 1,
            "similarity": 0.0,
            "method": "NO_GALLERY",
            "bbox": bbox
        }

    # =========================================================================
    # BƯỚC 1: LUÔN CHẠY FACENET512 TRƯỚC TIÊN
    # =========================================================================
    pv1 = extract_facenet_vector(face_crop)
    if pv1 is None:
        return {
            "status": "LOI_HE_THONG",
            "message": "Lỗi trích xuất vector FaceNet512",
            "num_faces": 1,
            "similarity": 0.0,
            "method": "FACENET_FAILED",
            "bbox": bbox
        }

    d1 = float(min(1.0 - np.dot(pv1, tv1) for tv1 in target_m1))
    sim1 = max(0.0, min(1.0, 1.0 - d1))

    # =========================================================================
    # BƯỚC 2: KIỂM TRA ĐIỀU KIỆN EARLY EXIT
    # =========================================================================
    if d1 <= 0.31:
        # VÙNG AN TOÀN TUYỆT ĐỐI -> CHO QUA LUÔN (KHÔNG GỌI ADAFACE & ARCFACE)
        pct = round(sim1 * 100, 1)
        return {
            "status": "DUNG_NGUOI",
            "message": f"Xác thực chính chủ thành công! ({pct}%)",
            "num_faces": 1,
            "similarity": round(sim1, 4),
            "distance": round(d1, 4),
            "method": "EARLY_EXIT_PASS",
            "bbox": bbox
        }

    elif d1 >= 0.42:
        # VÙNG NGOÀI AN TOÀN TUYỆT ĐỐI -> ĐÁNH TRƯỢT LUÔN
        pct = round(sim1 * 100, 1)
        return {
            "status": "KHONG_DUNG_NGUOI",
            "message": f"Khuôn mặt không khớp với hồ sơ thí sinh! ({pct}%)",
            "num_faces": 1,
            "similarity": round(sim1, 4),
            "distance": round(d1, 4),
            "method": "EARLY_EXIT_FAIL",
            "bbox": bbox
        }

    else:
        # =====================================================================
        # VÙNG RANH GIỚI (GRAY ZONE: 0.31 < d1 < 0.42)
        # KÍCH HOẠT HỘI CHẨN 2 NHÁNH PHỤ: ADAFACE + ARCFACE
        # =====================================================================
        print(f"[EarlyExit] d1={d1:.4f} nằm trong Gray Zone (0.31 - 0.42) -> Kích hoạt AdaFace & ArcFace...")

        if target_m2 and target_m3:
            pv2 = extract_adaface_vector(face_crop)
            pv3 = extract_arcface_vector(face_crop)

            if pv2 is not None and pv3 is not None:
                d2 = float(min(1.0 - np.dot(pv2, tv2) for tv2 in target_m2))
                d3 = float(min(1.0 - np.dot(pv3, tv3) for tv3 in target_m3))

                # Công thức dung hợp đề xuất của Trương Lê Hải Quân: 0.5*d1 + 0.25*d2 + 0.25*d3
                fusion_distance = (0.5 * d1) + (0.25 * d2) + (0.25 * d3)
                fusion_sim = max(0.0, min(1.0, 1.0 - fusion_distance))
                pct = round(fusion_sim * 100, 1)

                if fusion_distance <= 0.36:
                    return {
                        "status": "DUNG_NGUOI",
                        "message": f"Xác thực chính chủ thành công! ({pct}%)",
                        "num_faces": 1,
                        "similarity": round(fusion_sim, 4),
                        "distance": round(fusion_distance, 4),
                        "method": "TRIPLE_FUSION_PASS",
                        "bbox": bbox
                    }
                else:
                    return {
                        "status": "KHONG_DUNG_NGUOI",
                        "message": f"Khuôn mặt không khớp với hồ sơ thí sinh! ({pct}%)",
                        "num_faces": 1,
                        "similarity": round(fusion_sim, 4),
                        "distance": round(fusion_distance, 4),
                        "method": "TRIPLE_FUSION_FAIL",
                        "bbox": bbox
                    }

        # Nếu chưa có đủ gallery của AdaFace/ArcFace, fallback theo ngưỡng trung gian của FaceNet
        if d1 <= 0.36:
            return {
                "status": "DUNG_NGUOI",
                "message": f"Xác thực chính chủ thành công! ({round(sim1*100, 1)}%)",
                "num_faces": 1,
                "similarity": round(sim1, 4),
                "distance": round(d1, 4),
                "method": "FACENET_FALLBACK_PASS",
                "bbox": bbox
            }
        else:
            return {
                "status": "KHONG_DUNG_NGUOI",
                "message": f"Khuôn mặt không khớp với hồ sơ thí sinh! ({round(sim1*100, 1)}%)",
                "num_faces": 1,
                "similarity": round(sim1, 4),
                "distance": round(d1, 4),
                "method": "FACENET_FALLBACK_FAIL",
                "bbox": bbox
            }
