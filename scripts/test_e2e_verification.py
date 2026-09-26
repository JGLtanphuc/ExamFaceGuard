import sys
import os
import requests
import json
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_URL = "http://localhost:8000"

def test_invigilator_login():
    session = requests.Session()
    login_resp = session.post(
        f"{BASE_URL}/login",
        data={"ten_dang_nhap": "giamthi", "mat_khau": "123456"},
        allow_redirects=False
    )
    print("1. Giám thị đăng nhập:", login_resp.status_code, login_resp.headers.get("Location"))
    assert login_resp.status_code in [200, 302, 303], "Đăng nhập giám thị thất bại"

    # Kiểm tra truy cập trang giám thị
    dash_resp = session.get(f"{BASE_URL}/invigilator")
    print("2. Truy cập dashboard giám thị:", dash_resp.status_code)
    assert dash_resp.status_code == 200

def test_student_flow():
    session = requests.Session()
    # 1. Đăng nhập sinh viên sv001 (Phùng Tấn Phúc)
    login_resp = session.post(
        f"{BASE_URL}/login",
        data={"ten_dang_nhap": "sv001", "mat_khau": "123456"},
        allow_redirects=False
    )
    loc = login_resp.headers.get("Location", "")
    print("\n3. Sinh viên sv001 đăng nhập:", login_resp.status_code, loc)
    assert login_resp.status_code in [200, 302, 303]
    
    # Lấy token từ query param
    token = ""
    if "token=" in loc:
        token = loc.split("token=")[1].split("&")[0]
        session.headers.update({"Authorization": f"Bearer {token}"})

    # 2. Gửi ảnh khuôn mặt chính chủ
    img_path = "IMG_DATA/L01/2001230695_PhungTanPhuc/OP1.jpg"
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{img_b64}"

    verify_resp = session.post(
        f"{BASE_URL}/student/api/verify-face",
        json={"image_base64": data_uri}
    )
    print("4. Xác thực khuôn mặt CHÍNH CHỦ:", verify_resp.status_code, verify_resp.json())
    res = verify_resp.json()
    assert res.get("status") == "DUNG_NGUOI", f"Xác thực chính chủ không thành công: {res}"
    print("   -> Success:", res.get("success"), "| Method:", res.get("method"), "| Similarity:", res.get("similarity"))

    # 3. Gửi ảnh khuôn mặt NGƯỜI KHÁC
    other_img_path = "IMG_DATA/L01/2045240004_TangTruongAn/OP1.jpg"
    with open(other_img_path, "rb") as f:
        other_b64 = base64.b64encode(f.read()).decode("utf-8")
        other_uri = f"data:image/jpeg;base64,{other_b64}"

    verify_other = session.post(
        f"{BASE_URL}/student/api/verify-face",
        json={"image_base64": other_uri}
    )
    print("5. Xác thực khuôn mặt NGƯỜI KHÁC (THI HỘ):", verify_other.status_code, verify_other.json())
    res_other = verify_other.json()
    assert res_other.get("status") == "KHONG_DUNG_NGUOI", f"Bắt người lạ không đúng: {res_other}"
    print("   -> Success:", res_other.get("success"), "| Method:", res_other.get("method"), "| Similarity:", res_other.get("similarity"))

if __name__ == "__main__":
    print("=== BẮT ĐẦU KIỂM THỬ END-TO-END PIPELINE MỚI ===")
    test_invigilator_login()
    test_student_flow()
    print("\n=== TẤT CẢ KIỂM THỬ ĐÃ THÀNH CÔNG RỰC RỠ! ===")
