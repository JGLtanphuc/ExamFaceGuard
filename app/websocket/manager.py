import json
from typing import Dict, List, Set, Any
from fastapi import WebSocket


class ConnectionManager:
    """
    Quản lý kết nối WebSocket thời gian thực giữa:
    - Giám thị (Dashboard theo dõi phòng thi)
    - Sinh viên (Client gửi heartbeat / cập nhật)
    """

    def __init__(self):
        # Danh sách kết nối của giám thị theo MaPhienThi: {ma_phien_thi: [WebSocket, ...]}
        self.invigilator_connections: Dict[int, List[WebSocket]] = {}
        # Danh sách kết nối của sinh viên: {ma_sinh_vien: WebSocket}
        self.student_connections: Dict[str, WebSocket] = {}

    async def connect_invigilator(self, websocket: WebSocket, ma_phien_thi: int):
        await websocket.accept()
        if ma_phien_thi not in self.invigilator_connections:
            self.invigilator_connections[ma_phien_thi] = []
        self.invigilator_connections[ma_phien_thi].append(websocket)
        print(f"[WS] Giám thị kết nối vào phiên thi {ma_phien_thi}")

    def disconnect_invigilator(self, websocket: WebSocket, ma_phien_thi: int):
        if ma_phien_thi in self.invigilator_connections:
            if websocket in self.invigilator_connections[ma_phien_thi]:
                self.invigilator_connections[ma_phien_thi].remove(websocket)
        print(f"[WS] Giám thị ngắt kết nối phiên thi {ma_phien_thi}")

    async def connect_student(self, websocket: WebSocket, ma_sinh_vien: str):
        await websocket.accept()
        self.student_connections[ma_sinh_vien] = websocket
        print(f"[WS] Sinh viên {ma_sinh_vien} đã kết nối WebSocket")

    def disconnect_student(self, ma_sinh_vien: str):
        if ma_sinh_vien in self.student_connections:
            del self.student_connections[ma_sinh_vien]
        print(f"[WS] Sinh viên {ma_sinh_vien} ngắt kết nối WebSocket")

    async def broadcast_to_session(self, ma_phien_thi: int, message: Dict[str, Any]):
        """Gửi cập nhật tới tất cả giám thị đang xem phiên thi ma_phien_thi"""
        if ma_phien_thi in self.invigilator_connections:
            disconnected = []
            for ws in self.invigilator_connections[ma_phien_thi]:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                self.invigilator_connections[ma_phien_thi].remove(ws)


ws_manager = ConnectionManager()

