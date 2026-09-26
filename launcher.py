import os
import sys
import time
import re
import socket
import subprocess
import webbrowser
import threading

# Thiet lap UTF-8 output
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED_EXE = os.path.join(BASE_DIR, "cloudflared.exe")

def get_lan_ip() -> str:
    """Lay dia chi IP Wi-Fi/LAN noi bo"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def kill_port_process(port: int):
    """Giai phong cong nhanh chong bang netstat va taskkill"""
    try:
        out = subprocess.check_output("netstat -ano", shell=True, text=True, errors="replace")
        for line in out.splitlines():
            if f":{port} " in line and ("LISTENING" in line or "ESTABLISHED" in line):
                parts = line.strip().split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid() and int(pid) != 0:
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def main():
    print("=" * 76, flush=True)
    print("      HE THONG GIAM SAT THI CHONG THI HO (EARLY EXIT TRIPLE-BRANCH)", flush=True)
    print("=" * 76, flush=True)
    print(" [*] Dang kiem tra va giai phong cong mang (8000, 8443)...", flush=True)
    kill_port_process(8000)
    kill_port_process(8443)

    lan_ip = get_lan_ip()

    # 1. Khoi dong FastAPI server (run.py)
    print(" [*] Dang khoi dong may chu FastAPI (HTTP 8000 & HTTPS 8443)...", flush=True)
    server_log = open(os.path.join(BASE_DIR, "server.log"), "w", encoding="utf-8", errors="replace")
    server_process = subprocess.Popen(
        [sys.executable, "-u", "run.py"],
        cwd=BASE_DIR,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True
    )

    # 2. Khoi dong Cloudflare Tunnel
    tunnel_url = None
    tunnel_process = None

    if os.path.exists(CLOUDFLARED_EXE):
        print(" [*] Dang tao duong ham Cloudflare Tunnel (HTTPS mien phi toan cau)...", flush=True)
        tunnel_process = subprocess.Popen(
            [CLOUDFLARED_EXE, "tunnel", "--url", "http://localhost:8000"],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        def capture_tunnel():
            nonlocal tunnel_url
            for line in iter(tunnel_process.stdout.readline, ""):
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match and not tunnel_url:
                    tunnel_url = match.group(0)

        t = threading.Thread(target=capture_tunnel, daemon=True)
        t.start()

        # Cho toi da 10 giay de lay link Cloudflare
        start_wait = time.time()
        while time.time() - start_wait < 10 and not tunnel_url:
            time.sleep(0.5)

    # Cho server FastAPI san sang
    time.sleep(1.5)

    local_url = "http://localhost:8000/login"

    # In banner thong tin
    print("\n" + "=" * 76, flush=True)
    print("                HE THONG DA SAN SANG HOAT DONG!", flush=True)
    print("=" * 76, flush=True)
    print("\n [1] TRUY CAP CUC BO TREN MAY TINH NAY (Da tu dong mo trinh duyet):", flush=True)
    print(f"     -> {local_url}", flush=True)
    print(f"     -> Giam thi:  http://localhost:8000/invigilator", flush=True)
    print(f"     -> Sinh vien: http://localhost:8000/student", flush=True)

    print("\n [2] TRUY CAP TRONG MANG WI-FI NOI BO (LAPTOP / DIEN THOAI CUNG WI-FI):", flush=True)
    print(f"     -> Giam thi:  http://{lan_ip}:8000/invigilator", flush=True)
    print(f"     -> Camera:    https://{lan_ip}:8443/student", flush=True)

    if tunnel_url:
        print("\n [3] TRUY CAP TOAN CAU QUA INTERNET (KHONG CAN CHUNG WI-FI):", flush=True)
        print(f"     -> Link chinh thuc:  {tunnel_url}", flush=True)
        print(f"     -> Link Giam thi:    {tunnel_url}/invigilator", flush=True)
        print(f"     -> Link Thi sinh:    {tunnel_url}/student", flush=True)
        print("     (Dung link nay mo truc tiep tren dien thoai 4G/5G rat tien loi)", flush=True)
    else:
        print("\n [3] Cloudflare Tunnel: Dang khoi tao hoac mo truc tiep bang localhost.", flush=True)

    print("\n" + "-" * 76, flush=True)
    print(" THONG TIN DANG NHAP:", flush=True)
    print("  * Giam thi:  giamthi / 123456", flush=True)
    print("  * Thi sinh:  sv001   / 123456 (hoac nhap MSSV: 2001230695)", flush=True)
    print("=" * 76, flush=True)
    print(" [!] Nhan Ctrl + C de dung toan bo he thong bat cu luc nao.\n", flush=True)

    # Tu dong mo trinh duyet
    try:
        target_open = tunnel_url if tunnel_url else local_url
        webbrowser.open(target_open)
    except Exception:
        pass

    # Tao file shortcut HTML click-to-open o thu muc goc
    try:
        html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Truy Cập Hệ Thống Giám Sát Thi</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; text-align: center; }}
        .card {{ max-width: 600px; margin: 0 auto; background: #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        h1 {{ color: #38bdf8; margin-bottom: 24px; font-size: 24px; }}
        .btn {{ display: block; margin: 16px auto; padding: 14px 24px; background: #2563eb; color: #fff; text-decoration: none; border-radius: 10px; font-weight: bold; font-size: 16px; transition: 0.2s; }}
        .btn:hover {{ background: #1d4ed8; transform: translateY(-2px); }}
        .btn-green {{ background: #059669; }}
        .btn-green:hover {{ background: #047857; }}
        .info {{ margin-top: 24px; font-size: 14px; color: #94a3b8; text-align: left; background: #0f172a; padding: 16px; border-radius: 8px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Hệ Thống Giám Sát Thi Trực Tuyến</h1>
        {"<a class='btn btn-green' href='" + tunnel_url + "' target='_blank'>🌐 Mở Link Toàn Cầu (Cloudflare)</a>" if tunnel_url else ""}
        <a class="btn" href="http://localhost:8000/invigilator" target="_blank">💻 Mở Trang Giám Thị (Cục bộ)</a>
        <a class="btn" href="http://localhost:8000/student" target="_blank">📱 Mở Trang Thí Sinh (Cục bộ)</a>
        <div class="info">
            <strong>Tài khoản đăng nhập:</strong><br>
            • Giám thị: <code>giamthi</code> / <code>123456</code><br>
            • Thí sinh: <code>sv001</code> / <code>123456</code> (hoặc MSSV 2001230695)
        </div>
    </div>
</body>
</html>"""
        with open(os.path.join(BASE_DIR, "CLICK_DE_TRUY_CAP.html"), "w", encoding="utf-8") as f:
            f.write(html_content)
    except Exception:
        pass

    # Giu tien trinh chay va lang nghe Ctrl+C
    try:
        while True:
            time.sleep(1)
            if server_process.poll() is not None:
                print("\n[!] May chu da dung lai.", flush=True)
                break
    except KeyboardInterrupt:
        print("\n[*] Dang tat he thong...", flush=True)
    finally:
        if server_process and server_process.poll() is None:
            server_process.terminate()
        if tunnel_process and tunnel_process.poll() is None:
            tunnel_process.terminate()
        try:
            server_log.close()
        except Exception:
            pass
        print("[*] Da tat toan bo dich vu. Hen gap lai!", flush=True)

if __name__ == "__main__":
    main()
