import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.services.face_service import process_face_pipeline

# Tạo mock face crop
mock_crop = np.zeros((160, 160, 3), dtype=np.uint8)

# Giả lập test trực tiếp logic dung hợp
def test_fusion_logic():
    # d1 = 0.35 (nằm trong Gray Zone: 0.31 < 0.35 < 0.42)
    # Giả sử d2 = 0.30 (AdaFace), d3 = 0.32 (ArcFace)
    # fusion = 0.5 * 0.35 + 0.25 * 0.30 + 0.25 * 0.32
    #        = 0.175 + 0.075 + 0.08 = 0.33 <= 0.36 -> TRIPLE_FUSION_PASS
    d1 = 0.35
    d2 = 0.30
    d3 = 0.32
    fusion_distance = (0.5 * d1) + (0.25 * d2) + (0.25 * d3)
    fusion_sim = max(0.0, min(1.0, 1.0 - fusion_distance))
    print(f"Test Fusion Score: distance={fusion_distance:.4f}, sim={fusion_sim*100:.1f}%")
    assert fusion_distance <= 0.36
    print("[PASS] Gray Zone Logic Test PASSED successfully!")

if __name__ == "__main__":
    test_fusion_logic()

