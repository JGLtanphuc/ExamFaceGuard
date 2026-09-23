import os
import sys
import socket

sys.stdout.reconfigure(encoding='utf-8')
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .database.connection import engine, Base
from .routers import auth, student, invigilator, monitoring, report

# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="Hệ Thống Giám Sát Thi Chống Thi Hộ",
    description="Research Prototype: Nhận dạng khuôn mặt RetinaFace + FaceNet512, WebSocket Realtime, SQL Server",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount thư mục Static
current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Đăng ký các Routers
app.include_router(auth.router)
app.include_router(student.router)
app.include_router(invigilator.router)
app.include_router(monitoring.router)
app.include_router(report.router)


@app.get("/")
async def root():
    """Chuyển hướng trang chủ về /login"""
    return RedirectResponse(url="/login")


@app.on_event("startup")
async def on_startup():
    """Khởi động ứng dụng, nạp kết nối và hiển thị IP mạng LAN phục vụ demo"""
    # Lấy IP mạng LAN nội bộ
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "127.0.0.1"

    print("=" * 70)
    print(" HỆ THỐNG GIÁM SÁT THI CHỐNG THI HỘ ĐÃ KHỞI ĐỘNG THÀNH CÔNG")
    print("=" * 70)
    print(f"[*] Máy chủ cục bộ:   http://localhost:8000")
    print(f"[*] Mạng Wi-Fi / LAN:  http://{local_ip}:8000")
    print(f"[*] Trang Sinh Viên:  http://{local_ip}:8000/student")
    print(f"[*] Trang Giám Thị:   http://{local_ip}:8000/invigilator")
    print(f"[*] Báo Cáo:          http://{local_ip}:8000/invigilator/report")
    print("=" * 70)

    # Nạp trước (Pre-warm) mô hình RetinaFace & FaceNet512 trong background thread để tránh độ trễ frame đầu tiên
    def _warmup_ai_models():
        try:
            print("[AI Warmup] Đang nạp trước mô hình nhận diện khuôn mặt RetinaFace + FaceNet512...")
            import numpy as np
            from deepface import DeepFace
            dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
            DeepFace.represent(dummy_img, model_name="Facenet512", detector_backend="retinaface", enforce_detection=False)
            print("[AI Warmup] Tải xong mô hình AI (RetinaFace + FaceNet512)! Sẵn sàng giám sát thi.")
        except Exception as e:
            print(f"[AI Warmup] Lưu ý khi nạp trước: {e}")

    import asyncio
    from starlette.concurrency import run_in_threadpool
    asyncio.create_task(run_in_threadpool(_warmup_ai_models))

