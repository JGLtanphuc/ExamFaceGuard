import time
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from .event_service import record_alert_event
from ..websocket.manager import ws_manager


class CandidateMonitorState:
    """Theo dõi trạng thái và bộ lọc thời gian (Temporal Validation) của 1 thí sinh"""

    def __init__(self):
        self.no_face_consecutive_frames = 0
        self.no_face_start_time: Optional[float] = None

        self.mismatch_consecutive_count = 0

        self.multi_face_consecutive_frames = 0
        self.multi_face_start_time: Optional[float] = None

        self.total_alerts_count = 0
        self.last_status = "Chua dang nhap"
        self.last_similarity = 0.0
        self.last_num_faces = 0
        self.last_update_time = datetime.utcnow()
        self.last_snapshot_b64: Optional[str] = None


# Lưu trữ trạng thái in-memory cho các thí sinh theo ma_tham_gia
_monitor_states: Dict[int, CandidateMonitorState] = {}


def get_or_create_state(ma_tham_gia: int) -> CandidateMonitorState:
    if ma_tham_gia not in _monitor_states:
        _monitor_states[ma_tham_gia] = CandidateMonitorState()
    return _monitor_states[ma_tham_gia]


async def evaluate_and_update_monitoring(
    db: Session,
    ma_tham_gia: int,
    ma_phien_thi: int,
    ma_sinh_vien: str,
    mssv: str,
    ho_ten: str,
    ma_pc: str,
    raw_status: str,
    similarity: float,
    num_faces: int,
    frame_b64: Optional[str],
    cfg_no_face_seconds: int,
    cfg_mismatch_count: int,
    cfg_multi_face_seconds: int
) -> Dict[str, Any]:
    """
    Áp dụng Temporal Validation để quyết định trạng thái và phát sinh cảnh báo:
    - Tránh cảnh báo giả khi chớp mắt hay quay đầu 1 frame.
    - Cảnh báo và ghi SuKienCanhBao khi vi phạm liên tục vượt ngưỡng cấu hình của kỳ thi.
    - Phát thông điệp cập nhật qua WebSocket tới Dashboard giám thị.
    """
    state = get_or_create_state(ma_tham_gia)
    now = time.time()
    current_time_str = datetime.now().strftime("%H:%M:%S")

    is_alert = False
    alert_type = None
    alert_message = ""
    display_status = raw_status

    # 1. Xử lý trường hợp: KHÔNG PHÁT HIỆN KHUÔN MẶT
    if raw_status == "KHONG_PHAT_HIEN_KHUON_MAT":
        state.mismatch_consecutive_count = 0
        state.multi_face_consecutive_frames = 0
        state.multi_face_start_time = None

        state.no_face_consecutive_frames += 1
        if state.no_face_start_time is None:
            state.no_face_start_time = now

        duration_no_face = now - state.no_face_start_time
        if duration_no_face >= cfg_no_face_seconds:
            is_alert = True
            alert_type = "KHONG_PHAT_HIEN_KHUON_MAT"
            alert_message = f"Không phát hiện khuôn mặt liên tục {int(duration_no_face)}s"
            display_status = "Không phát hiện khuôn mặt"
        else:
            display_status = "Đang kiểm tra mặt..."

    # 2. Xử lý trường hợp: KHÔNG ĐÚNG NGƯỜI
    elif raw_status == "KHONG_DUNG_NGUOI":
        state.no_face_consecutive_frames = 0
        state.no_face_start_time = None
        state.multi_face_consecutive_frames = 0
        state.multi_face_start_time = None

        state.mismatch_consecutive_count += 1
        if state.mismatch_consecutive_count >= cfg_mismatch_count:
            is_alert = True
            alert_type = "KHONG_DUNG_NGUOI"
            alert_message = f"Không đúng người {state.mismatch_consecutive_count} lần liên tiếp (Sim: {similarity})"
            display_status = "Không đúng người"
        else:
            display_status = "Đang kiểm tra độ khớp..."

    # 3. Xử lý trường hợp: PHÁT HIỆN NHIỀU KHUÔN MẶT
    elif raw_status == "PHAT_HIEN_NHIEU_KHUON_MAT":
        state.no_face_consecutive_frames = 0
        state.no_face_start_time = None
        state.mismatch_consecutive_count = 0

        state.multi_face_consecutive_frames += 1
        if state.multi_face_start_time is None:
            state.multi_face_start_time = now

        duration_multi = now - state.multi_face_start_time
        if duration_multi >= cfg_multi_face_seconds:
            is_alert = True
            alert_type = "PHAT_HIEN_NHIEU_KHUON_MAT"
            alert_message = f"Phát hiện {num_faces} khuôn mặt liên tục {int(duration_multi)}s"
            display_status = "Phát hiện nhiều khuôn mặt"
        else:
            display_status = "Nghi vấn nhiều người..."

    # 4. Xử lý trường hợp: ĐÚNG NGƯỜI
    elif raw_status == "DUNG_NGUOI":
        # Reset các bộ đếm vi phạm
        state.no_face_consecutive_frames = 0
        state.no_face_start_time = None
        state.mismatch_consecutive_count = 0
        state.multi_face_consecutive_frames = 0
        state.multi_face_start_time = None

        display_status = "Đúng người"

    # 5. Xử lý trường hợp: CAMERA LỖI
    elif raw_status == "LOI_CAMERA":
        is_alert = True
        alert_type = "LOI_CAMERA"
        alert_message = "Camera bị mất tín hiệu hoặc gặp lỗi"
        display_status = "Camera bị lỗi"

    # Cập nhật state
    state.last_status = display_status
    state.last_similarity = similarity
    state.last_num_faces = num_faces
    state.last_update_time = datetime.utcnow()
    if frame_b64:
        state.last_snapshot_b64 = frame_b64

    # Nếu phát sinh cảnh báo -> ghi vào SuKienCanhBao
    if is_alert and alert_type:
        state.total_alerts_count += 1
        try:
            record_alert_event(
                db=db,
                ma_tham_gia=ma_tham_gia,
                loai_su_kien=alert_type,
                do_tuong_dong=similarity if similarity > 0 else None,
                so_khuon_mat=num_faces,
                thoi_luong_giay=1,
                snapshot_path=None,
                ghi_chu=alert_message
            )
        except Exception as e:
            print(f"[Monitoring] Lỗi lưu SuKienCanhBao: {e}")

    # Chuẩn bị dữ liệu cập nhật gửi qua WebSocket cho Giám thị
    ws_payload = {
        "event": "STUDENT_UPDATE",
        "data": {
            "ma_tham_gia": ma_tham_gia,
            "ma_sinh_vien": ma_sinh_vien,
            "mssv": mssv,
            "ho_ten": ho_ten,
            "ma_pc": ma_pc,
            "trang_thai": display_status,
            "do_tuong_dong": similarity,
            "so_khuon_mat": num_faces,
            "thoi_gian": current_time_str,
            "is_alert": is_alert,
            "alert_type": alert_type,
            "alert_message": alert_message,
            "total_alerts": state.total_alerts_count,
            "frame_preview": frame_b64 if frame_b64 else None
        }
    }

    # Bắn WebSocket realtime tới Dashboard
    await ws_manager.broadcast_to_session(ma_phien_thi, ws_payload)

    return ws_payload["data"]

