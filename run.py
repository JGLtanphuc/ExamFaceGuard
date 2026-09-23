import sys
import os
import asyncio
import datetime
import ipaddress
import uvicorn
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_FILE = os.path.join(BASE_DIR, "cert.pem")
KEY_FILE = os.path.join(BASE_DIR, "key.pem")


import socket

def get_current_ip() -> str:
    """Tự động phát hiện IP LAN/Wi-Fi của máy chủ"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def ensure_ssl_certs():
    """Tự động sinh chứng chỉ SSL tự ký nếu chưa có để hỗ trợ Camera Realtime trên thiết bị di động"""
    cur_ip = get_current_ip()
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return

    print(f"[SSL] Đang khởi tạo chứng chỉ SSL cho máy chủ ({cur_ip})...")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "VN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Giam Sat Thi Chống Thi Hộ"),
        x509.NameAttribute(NameOID.COMMON_NAME, cur_ip),
    ])
    san = x509.SubjectAlternativeName([
        x509.IPAddress(ipaddress.IPv4Address(cur_ip)),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.DNSName("localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )
    with open(KEY_FILE, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()
        ))
    with open(CERT_FILE, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("[SSL] Chứng chỉ SSL đã được tạo thành công.")


async def start_dual_servers():
    ensure_ssl_certs()
    cur_ip = get_current_ip()

    # Máy chủ 1: HTTP chuẩn (Cổng 8000)
    config_http = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False
    )
    # Máy chủ 2: HTTPS bảo mật (Cổng 8443) - Bắt buộc cho Camera Realtime trên Điện thoại (iOS / Android)
    config_https = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=8443,
        ssl_certfile=CERT_FILE,
        ssl_keyfile=KEY_FILE,
        log_level="info",
        reload=False
    )

    server_http = uvicorn.Server(config_http)
    server_https = uvicorn.Server(config_https)

    print("=" * 72)
    print(" HỆ THỐNG GIÁM SÁT THI - SẴN SÀNG CHẠY SONG SONG HTTP & HTTPS")
    print("=" * 72)
    print(f" [*] Máy chủ Laptop (Cục bộ):        http://localhost:8000")
    print(f" [*] Máy chủ Mạng LAN (Giám thị):    http://{cur_ip}:8000")
    print(f" [*] Camera HTTPS (Điện thoại):      https://{cur_ip}:8443")
    print("-" * 72)
    print(f" [*] Đăng nhập Thí sinh (Mobile):    https://{cur_ip}:8443/student")
    print(f" [*] Bảng Giám thị (Laptop):         http://localhost:8000/invigilator")
    print(f" [*] Báo cáo thống kê:               http://localhost:8000/invigilator/report")
    print("=" * 72)

    await asyncio.gather(
        server_http.serve(),
        server_https.serve()
    )


if __name__ == "__main__":
    asyncio.run(start_dual_servers())
