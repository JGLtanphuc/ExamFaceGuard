import io
from datetime import datetime
from typing import Dict, Any, List, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database.models import (
    PhienThi, PhongThi, CaThi, KyThi, ThiSinhTrongPhien, SinhVien, MayTram, SuKienCanhBao
)


def get_session_report(db: Session, ma_phien_thi: int) -> Dict[str, Any]:
    """
    Tổng hợp báo cáo điểm danh & đối sánh khuôn mặt thí sinh phiên thi:
    - Tổng sinh viên
    - Số sinh viên xác thực hợp lệ & tham gia thi
    - Số ca nghi vấn thi hộ lúc check-in
    - Số bài đã nộp
    - Số sinh viên vắng thi
    - Danh sách chi tiết từng thí sinh (STT, MSSV, Họ tên, Máy trạm, Ảnh, Độ tương đồng, Kết quả, Trạng thái)
    - Danh sách các sự kiện cảnh báo (nếu có)
    """
    phien = db.query(PhienThi).filter(PhienThi.MaPhienThi == ma_phien_thi).first()
    if not phien:
        return {}

    phong = db.query(PhongThi).filter(PhongThi.MaPhong == phien.MaPhong).first()
    ca = db.query(CaThi).filter(CaThi.MaCa == phien.MaCa).first()
    ky = db.query(KyThi).filter(KyThi.MaKyThi == phien.MaKyThi).first()

    records = db.query(
        ThiSinhTrongPhien, SinhVien, MayTram
    ).join(
        SinhVien, SinhVien.MaSinhVien == ThiSinhTrongPhien.MaSinhVien
    ).outerjoin(
        MayTram, MayTram.MaMay == ThiSinhTrongPhien.MaMay
    ).filter(
        ThiSinhTrongPhien.MaPhienThi == ma_phien_thi
    ).order_by(
        SinhVien.STT
    ).all()

    total_candidates = len(records)
    attended_count = 0
    suspect_count = 0
    submitted_count = 0
    absent_count = 0

    candidate_list = []
    candidate_ids = []

    for ts, sv, mt in records:
        candidate_ids.append(ts.MaThamGia)
        status = ts.TrangThai or "Chua dang nhap"
        sim = float(ts.DoTuongDongXacThuc) if ts.DoTuongDongXacThuc is not None else None

        # Phân loại số liệu
        if status in ["Dang thi", "Da nop", "Da ket thuc"]:
            attended_count += 1
            if status in ["Da nop", "Da ket thuc"]:
                submitted_count += 1
        elif status in ["Nghi van thi ho", "Xac thuc that bai"]:
            suspect_count += 1
        elif status in ["Chua dang nhap", "Ngoai tuyen", "Da dang xuat"]:
            absent_count += 1

        # Đánh giá kết quả đối sánh khuôn mặt
        if sim is not None:
            if sim >= 0.70:
                ket_qua = "Hợp lệ"
                ghi_chu = f"Xác thực khuôn mặt đạt {sim*100:.1f}% (≥ 70%)"
            else:
                ket_qua = "Nghi vấn thi hộ"
                ghi_chu = f"Độ tương đồng {sim*100:.1f}% dưới ngưỡng 70%"
        elif status == "Dang xac thuc":
            ket_qua = "Đang xác thực"
            ghi_chu = "Thí sinh đang quét khuôn mặt"
        else:
            ket_qua = "Chưa xác thực"
            ghi_chu = "Chưa đăng nhập / vắng thi"

        # Trạng thái hiển thị tiếng Việt
        trang_thai_map = {
            "Chua dang nhap": "Chưa đăng nhập",
            "Dang xac thuc": "Đang xác thực",
            "Dang thi": "Đang thi",
            "Da nop": "Đã nộp bài",
            "Da ket thuc": "Đã kết thúc",
            "Da dang xuat": "Đã đăng xuất",
            "Ngoai tuyen": "Ngoại tuyến",
            "Nghi van thi ho": "Nghi vấn thi hộ",
            "Xac thuc that bai": "Xác thực thất bại"
        }

        candidate_list.append({
            "stt": sv.STT,
            "mssv": sv.MSSV,
            "ho_ten": sv.HoTen,
            "ma_pc": mt.MaPC if mt else "Chưa gán",
            "thoi_gian": ts.ThoiGianDangNhap.strftime("%d/%m/%Y %H:%M:%S") if ts.ThoiGianDangNhap else "--",
            "do_tuong_dong": sim,
            "anh_xac_thuc": ts.AnhXacThuc,
            "ket_qua_xac_thuc": ket_qua,
            "trang_thai_bai_thi": trang_thai_map.get(status, status),
            "ghi_chu": ghi_chu
        })

    # Lấy danh sách sự kiện cảnh báo (nếu có)
    alert_details = []
    if candidate_ids:
        raw_events = db.query(
            SuKienCanhBao, SinhVien
        ).join(
            ThiSinhTrongPhien, ThiSinhTrongPhien.MaThamGia == SuKienCanhBao.MaThamGia
        ).join(
            SinhVien, SinhVien.MaSinhVien == ThiSinhTrongPhien.MaSinhVien
        ).filter(
            ThiSinhTrongPhien.MaPhienThi == ma_phien_thi
        ).order_by(
            SuKienCanhBao.ThoiGianBatDau.desc()
        ).all()

        for ev, sv in raw_events:
            alert_details.append({
                "ma_su_kien": ev.MaSuKien,
                "mssv": sv.MSSV,
                "ho_ten": sv.HoTen,
                "loai_su_kien": ev.LoaiSuKien,
                "do_tuong_dong": float(ev.DoTuongDong) if ev.DoTuongDong is not None else None,
                "so_khuon_mat": ev.SoKhuonMat,
                "thoi_gian": ev.ThoiGianBatDau.strftime("%d/%m/%Y %H:%M:%S") if ev.ThoiGianBatDau else "",
                "ghi_chu": ev.GhiChu or ""
            })

    return {
        "ma_phien_thi": ma_phien_thi,
        "ten_ky_thi": ky.TenKyThi if ky else "",
        "ten_phong": phong.TenPhong if phong else "",
        "ten_ca": ca.TenCa if ca else "",
        "gio_thi": f"{ca.GioBatDau} - {ca.GioKetThuc}" if ca else "",
        "tong_sinh_vien": total_candidates,
        "so_sv_tham_gia": attended_count,
        "so_ca_nghi_van": suspect_count,
        "so_sv_da_nop": submitted_count,
        "so_sv_vang_thi": absent_count,
        "tong_canh_bao": len(alert_details),
        "danh_sach_thi_sinh": candidate_list,
        "danh_sach_su_kien": alert_details
    }


def generate_excel_report(report_data: Dict[str, Any], candidates: Optional[List[Dict[str, Any]]] = None) -> io.BytesIO:
    """
    Xuất Biên Bản Điểm Danh & Đối Sánh Khuôn Mặt Thí Sinh ra file Excel (.xlsx) chuẩn Executive:
    - Các cột: STT, Thời Gian, MSSV, Họ và Tên, Máy Trạm, Độ Tương Đồng, Kết Quả Đối Sánh, Trạng Thái, Ghi Chú
    - Header xanh navy trang trọng, viền ô sắc nét, font chữ Calibri chuẩn
    - Tự động căn lề và tính toán độ rộng cột tối ưu
    - Kèm dòng tổng kết số lượng thí sinh
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DiemDanh_XacThuc"
    ws.views.sheetView[0].showGridLines = True

    ten_phong = report_data.get("ten_phong", "Phòng Thi")
    ten_ca = report_data.get("ten_ca", "Ca Thi")
    gio_thi = report_data.get("gio_thi", "--")
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # 1. Header Banner
    ws["A1"] = "BỘ CÔNG THƯƠNG - TRƯỜNG ĐẠI HỌC CÔNG THƯƠNG TP. HỒ CHÍ MINH"
    ws["A1"].font = Font(name="Calibri", size=10, bold=True, color="1E3A8A")

    ws["A2"] = "BIÊN BẢN ĐIỂM DANH & ĐỐI SÁNH KHUÔN MẶT THÍ SINH PHÒNG THI"
    ws["A2"].font = Font(name="Calibri", size=14, bold=True, color="0F172A")

    ws["A3"] = f"Phòng Thi: {ten_phong}   |   Ca Thi: {ten_ca} ({gio_thi})   |   Thời Điểm Xuất: {now_str}"
    ws["A3"].font = Font(name="Calibri", size=10, italic=True, color="475569")

    # 2. Table Headers
    headers = [
        "STT",
        "Thời Gian Check-in",
        "MSSV",
        "Họ và Tên",
        "Độ Tương Đồng",
        "Kết Quả Đối Sánh",
        "Trạng Thái Bài Thi",
        "Ghi Chú"
    ]

    header_row = 5
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    alert_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    ws.row_dimensions[header_row].height = 26

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    # 3. Data Rows
    candidate_items = candidates if candidates is not None else report_data.get("danh_sach_thi_sinh", [])

    current_row = 6
    for idx, c in enumerate(candidate_items, 1):
        ws.row_dimensions[current_row].height = 22

        sim_val = c.get("do_tuong_dong")
        if sim_val is not None:
            try:
                val_float = float(sim_val)
                sim_text = f"{val_float * 100:.1f}%" if val_float <= 1.0 else f"{val_float:.1f}%"
            except (ValueError, TypeError):
                sim_text = str(sim_val)
        else:
            sim_text = "--"

        ket_qua = c.get("ket_qua_xac_thuc") or "--"
        is_suspect = "nghi vấn" in ket_qua.lower() or "thất bại" in ket_qua.lower()
        row_fill = alert_fill if is_suspect else (zebra_fill if idx % 2 == 0 else white_fill)

        row_data = [
            (c.get("stt") or idx, "center", False),
            (c.get("thoi_gian") or "--", "center", False),
            (str(c.get("mssv") or ""), "center", True),
            (c.get("ho_ten") or "", "left", True),
            (sim_text, "center", False),
            (ket_qua, "center", is_suspect),
            (c.get("trang_thai_bai_thi") or "--", "center", False),
            (c.get("ghi_chu") or "", "left", False)
        ]

        for col_idx, (val, align_h, is_bold) in enumerate(row_data, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            text_color = "B91C1C" if (is_suspect and col_idx in [6, 7]) else "0F172A"
            cell.font = Font(name="Calibri", size=10, bold=is_bold, color=text_color)
            cell.alignment = Alignment(horizontal=align_h, vertical="center", wrap_text=(col_idx == 8))
            cell.border = thin_border
            cell.fill = row_fill

        current_row += 1

    # 4. Total Summary Row
    summary_row = current_row
    ws.row_dimensions[summary_row].height = 24
    ws.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=4)

    total_candidates = report_data.get("tong_sinh_vien", len(candidate_items))
    attended = report_data.get("so_sv_tham_gia", 0)
    suspect = report_data.get("so_ca_nghi_van", 0)
    absent = report_data.get("so_sv_vang_thi", 0)

    summary_text = f"TỔNG CỘNG: {total_candidates} THÍ SINH  |  {attended} THAM GIA DỰ THI  |  {suspect} NGHI VẤN THI HỘ  |  {absent} VẮNG THI"
    summary_cell = ws.cell(row=summary_row, column=1, value=summary_text)
    summary_cell.font = Font(name="Calibri", size=10, bold=True, color="1E3A8A")
    summary_cell.alignment = Alignment(horizontal="left", vertical="center")

    for col_idx in range(1, 9):
        ws.cell(row=summary_row, column=col_idx).border = thin_border
        ws.cell(row=summary_row, column=col_idx).fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")

    # 5. Column Widths
    col_widths = {
        "A": 8,   # STT
        "B": 22,  # Thời Gian
        "C": 16,  # MSSV
        "D": 28,  # Họ và Tên
        "E": 18,  # Độ Tương Đồng
        "F": 24,  # Kết Quả Đối Sánh
        "G": 20,  # Trạng Thái Bài Thi
        "H": 40   # Ghi Chú
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    # 6. Freeze Panes & AutoFilter
    ws.freeze_panes = "A6"
    if len(candidate_items) > 0:
        ws.auto_filter.ref = f"A5:H{current_row - 1}"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
