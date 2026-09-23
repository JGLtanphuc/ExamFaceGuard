/**
 * report.js - Báo Cáo Điểm Danh & Đối Sánh Khuôn Mặt Thí Sinh Phòng Thi
 * Hệ thống Điểm danh Xác thực Khuôn mặt (RetinaFace + FaceNet512)
 */

document.addEventListener("DOMContentLoaded", () => {
  const reportData = window.REPORT_DATA || {};
  const allCandidates = Array.isArray(reportData.danh_sach_thi_sinh) ? reportData.danh_sach_thi_sinh : [];

  // DOM Elements
  const roomSelect = document.getElementById("report-room");
  const shiftSelect = document.getElementById("report-shift");
  const searchInput = document.getElementById("candidate-search-input");
  const tabPills = document.querySelectorAll(".tab-pill");
  const pageSizeSelect = document.getElementById("page-size-select");
  const tbody = document.getElementById("candidates-tbody");
  const filteredBadge = document.getElementById("filtered-count-badge");
  const paginationInfo = document.getElementById("pagination-info");
  const paginationControls = document.getElementById("pagination-controls");
  const btnExportExcel = document.getElementById("btn-export-excel");
  const btnPrintReport = document.getElementById("btn-print-report");

  // State
  let currentFilter = "ALL";
  let searchQuery = "";
  let currentPage = 1;
  let pageSize = parseInt(pageSizeSelect ? pageSizeSelect.value : "15", 10) || 15;

  // Helper: Bỏ dấu tiếng Việt phục vụ tìm kiếm
  function removeVietnameseTones(str) {
    if (!str) return "";
    str = String(str).toLowerCase();
    str = str.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    str = str.replace(/đ/g, "d");
    return str;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function getInitials(name) {
    if (!name) return "SV";
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return parts[parts.length - 1][0].toUpperCase();
  }

  // 1. Lọc và Tìm kiếm danh sách thí sinh
  function getFilteredCandidates() {
    const rawSearch = searchQuery.trim();
    const cleanSearch = removeVietnameseTones(rawSearch);

    return allCandidates.filter(c => {
      const status = (c.trang_thai_bai_thi || "").toLowerCase();
      const verdict = (c.ket_qua_xac_thuc || "").toLowerCase();

      // Lọc theo Tab
      if (currentFilter === "ATTENDED") {
        if (!status.includes("đang thi") && !status.includes("đã nộp") && !status.includes("kết thúc")) return false;
      } else if (currentFilter === "SUSPECT") {
        if (!verdict.includes("nghi vấn") && !status.includes("nghi vấn") && !verdict.includes("thất bại")) return false;
      } else if (currentFilter === "SUBMITTED") {
        if (!status.includes("đã nộp") && !status.includes("kết thúc")) return false;
      } else if (currentFilter === "ABSENT") {
        if (!status.includes("chưa") && !status.includes("đăng xuất") && !status.includes("ngoại tuyến")) return false;
      }

      // Lọc theo từ khóa tìm kiếm
      if (rawSearch) {
        const mssvStr = String(c.mssv || "").toLowerCase();
        const hoTenStr = String(c.ho_ten || "").toLowerCase();
        const noteStr = String(c.ghi_chu || "").toLowerCase();

        const cleanHoTen = removeVietnameseTones(hoTenStr);
        const cleanNote = removeVietnameseTones(noteStr);

        const matchDirect = mssvStr.includes(rawSearch.toLowerCase()) ||
                            hoTenStr.includes(rawSearch.toLowerCase()) ||
                            noteStr.includes(rawSearch.toLowerCase());

        const matchUnaccented = cleanHoTen.includes(cleanSearch) ||
                                cleanNote.includes(cleanSearch) ||
                                mssvStr.includes(cleanSearch);

        if (!matchDirect && !matchUnaccented) {
          return false;
        }
      }

      return true;
    });
  }

  // 2. Render bảng danh sách thí sinh
  function renderTable() {
    if (!tbody) return;

    const filtered = getFilteredCandidates();
    const totalItems = filtered.length;

    if (filteredBadge) {
      filteredBadge.textContent = `${totalItems} thí sinh`;
    }

    if (totalItems === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" style="text-align: center; padding: 3rem 1rem; color: var(--text-sub);">
            <div style="font-size: 2rem; margin-bottom: 0.35rem;">🔍</div>
            <strong style="color: #334155; font-size: 1rem;">Không tìm thấy thí sinh phù hợp</strong>
            <p style="margin: 0.25rem 0 0; font-size: 0.85rem;">Thử thay đổi từ khóa tìm kiếm hoặc chọn tab phân loại khác.</p>
          </td>
        </tr>
      `;
      renderPagination(0, 0, 0);
      return;
    }

    // Phân trang
    let startIdx = 0;
    let endIdx = totalItems;
    let displayItems = filtered;

    if (pageSize < 9999) {
      const totalPages = Math.ceil(totalItems / pageSize);
      if (currentPage > totalPages) currentPage = totalPages;
      if (currentPage < 1) currentPage = 1;

      startIdx = (currentPage - 1) * pageSize;
      endIdx = Math.min(startIdx + pageSize, totalItems);
      displayItems = filtered.slice(startIdx, endIdx);
    }

    tbody.innerHTML = displayItems.map(c => {
      const isSuspect = (c.ket_qua_xac_thuc && c.ket_qua_xac_thuc.toLowerCase().includes("nghi vấn")) ||
                        (c.trang_thai_bai_thi && c.trang_thai_bai_thi.toLowerCase().includes("nghi vấn"));

      // Thumbnail check-in
      let thumbHtml = '<span style="color: var(--text-sub); font-size: 0.75rem;">--</span>';
      if (c.anh_xac_thuc) {
        const simPct = c.do_tuong_dong ? (c.do_tuong_dong * 100).toFixed(1) + "%" : "--";
        thumbHtml = `
          <img src="${c.anh_xac_thuc}" alt="Ảnh xác thực" class="snapshot-thumb" title="Bấm để xem ảnh lớn"
               onclick="openPhotoModal('${escapeHtml(c.ho_ten)}', '${escapeHtml(c.mssv)}', '${c.anh_xac_thuc}', '${simPct}')">
        `;
      }

      // Gauge độ tương đồng
      let simHtml = `<span style="color: #94a3b8; font-style: italic;">--</span>`;
      if (c.do_tuong_dong !== null && c.do_tuong_dong !== undefined) {
        const pct = Math.round(c.do_tuong_dong * 100);
        const color = pct >= 70 ? "var(--success)" : "var(--danger)";
        simHtml = `
          <div class="sim-gauge-cell" title="Độ khớp khuôn mặt: ${(c.do_tuong_dong * 100).toFixed(1)}%">
            <div class="sim-track">
              <div class="sim-fill" style="width: ${Math.min(100, Math.max(0, pct))}%; background-color: ${color};"></div>
            </div>
            <span class="sim-val-text" style="color: ${color};">${(c.do_tuong_dong * 100).toFixed(1)}%</span>
          </div>
        `;
      }

      // Badge kết quả đối sánh
      let verdictBadgeClass = "badge-slate";
      let verdictIcon = "⚪";
      if (c.ket_qua_xac_thuc === "Hợp lệ") {
        verdictBadgeClass = "badge-success";
        verdictIcon = "✅";
      } else if (isSuspect) {
        verdictBadgeClass = "badge-danger";
        verdictIcon = "⚠️";
      } else if (c.ket_qua_xac_thuc === "Đang xác thực") {
        verdictBadgeClass = "badge-warning";
        verdictIcon = "⏳";
      }

      // Badge trạng thái bài thi
      let statusBadgeClass = "badge-slate";
      if (c.trang_thai_bai_thi === "Đang thi") statusBadgeClass = "badge-success";
      else if (c.trang_thai_bai_thi === "Đã nộp bài") statusBadgeClass = "badge-slate";
      else if (isSuspect) statusBadgeClass = "badge-danger";

      return `
        <tr class="${isSuspect ? 'row-alert' : ''}">
          <td data-label="STT" style="text-align: center; font-weight: 700; color: var(--text-sub);">
            ${c.stt || '--'}
          </td>

          <td data-label="Thời Gian Check-in">
            <span style="font-family: monospace; font-size: 0.82rem; color: #334155;">
              ${escapeHtml(c.thoi_gian)}
            </span>
          </td>

          <td data-label="Thí Sinh">
            <div class="candidate-info-cell">
              <div class="avatar-mini">${getInitials(c.ho_ten)}</div>
              <div>
                <div class="mssv-bold">${escapeHtml(c.mssv)}</div>
                <div class="student-name-text">${escapeHtml(c.ho_ten)}</div>
              </div>
            </div>
          </td>

          <td data-label="Ảnh Check-in" style="text-align: center;">
            ${thumbHtml}
          </td>

          <td data-label="Độ Tương Đồng">
            ${simHtml}
          </td>

          <td data-label="Kết Quả Đối Sánh">
            <span class="status-badge-modern ${verdictBadgeClass}">
              <span>${verdictIcon}</span>
              <span>${escapeHtml(c.ket_qua_xac_thuc || '--')}</span>
            </span>
          </td>

          <td data-label="Trạng Thái Bài Thi">
            <span class="status-badge-modern ${statusBadgeClass}">
              ${escapeHtml(c.trang_thai_bai_thi || '--')}
            </span>
          </td>

          <td data-label="Ghi Chú">
            <span style="font-size: 0.8rem; color: #475569;">
              ${escapeHtml(c.ghi_chu || '')}
            </span>
          </td>
        </tr>
      `;
    }).join("");

    renderPagination(totalItems, startIdx, endIdx);
  }

  // 3. Render Pagination
  function renderPagination(totalItems, startIdx, endIdx) {
    if (!paginationInfo || !paginationControls) return;

    if (totalItems === 0) {
      paginationInfo.textContent = "Hiển thị 0 thí sinh";
      paginationControls.innerHTML = "";
      return;
    }

    paginationInfo.textContent = `Hiển thị ${startIdx + 1} - ${endIdx} trong tổng số ${totalItems} thí sinh`;

    if (pageSize >= 9999 || totalItems <= pageSize) {
      paginationControls.innerHTML = "";
      return;
    }

    const totalPages = Math.ceil(totalItems / pageSize);
    let html = "";

    // Nút trước
    html += `<button type="button" class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">◀</button>`;

    // Các số trang
    for (let p = 1; p <= totalPages; p++) {
      if (p === 1 || p === totalPages || (p >= currentPage - 2 && p <= currentPage + 2)) {
        html += `<button type="button" class="page-btn ${p === currentPage ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`;
      } else if (p === currentPage - 3 || p === currentPage + 3) {
        html += `<span style="padding: 0 0.25rem; color: var(--text-sub);">...</span>`;
      }
    }

    // Nút sau
    html += `<button type="button" class="page-btn ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">▶</button>`;

    paginationControls.innerHTML = html;
  }

  window.goToPage = function(page) {
    const filtered = getFilteredCandidates();
    const totalPages = Math.ceil(filtered.length / pageSize);
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    renderTable();
  };

  // 4. Lắng nghe sự kiện
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      searchQuery = e.target.value;
      currentPage = 1;
      renderTable();
    });
  }

  tabPills.forEach(pill => {
    pill.addEventListener("click", () => {
      tabPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentFilter = pill.getAttribute("data-filter") || "ALL";
      currentPage = 1;
      renderTable();
    });
  });

  if (pageSizeSelect) {
    pageSizeSelect.addEventListener("change", (e) => {
      pageSize = parseInt(e.target.value, 10) || 15;
      currentPage = 1;
      renderTable();
    });
  }

  // Chuyển phòng thi & ca thi
  function onSessionChange() {
    const roomId = roomSelect.value;
    const shiftId = shiftSelect.value;
    window.location.href = `/invigilator/report?room_id=${roomId}&shift_id=${shiftId}`;
  }

  if (roomSelect) roomSelect.addEventListener("change", onSessionChange);
  if (shiftSelect) shiftSelect.addEventListener("change", onSessionChange);

  // Xuất file Excel
  if (btnExportExcel) {
    btnExportExcel.addEventListener("click", () => {
      const roomId = roomSelect ? roomSelect.value : 1;
      const shiftId = shiftSelect ? shiftSelect.value : 1;
      window.location.href = `/invigilator/report/export-excel?room_id=${roomId}&shift_id=${shiftId}`;
    });
  }

  // In / Xuất PDF
  if (btnPrintReport) {
    btnPrintReport.addEventListener("click", () => {
      window.print();
    });
  }

  // Khởi chạy render ban đầu
  renderTable();
});

// Modal xem ảnh lớn
window.openPhotoModal = function(name, mssv, imgUrl, simText) {
  const modal = document.getElementById("photo-modal");
  if (!modal) return;

  const modalImg = document.getElementById("modal-img");
  const modalTitle = document.getElementById("modal-title");
  const modalMeta = document.getElementById("modal-meta");

  if (modalImg) modalImg.src = imgUrl || "";
  if (modalTitle) modalTitle.textContent = `Ảnh Check-in: ${name}`;
  if (modalMeta) modalMeta.textContent = `MSSV: ${mssv} • Độ khớp: ${simText}`;

  modal.style.display = "flex";
};

window.closePhotoModal = function(e) {
  const modal = document.getElementById("photo-modal");
  if (modal) {
    modal.style.display = "none";
  }
};

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    window.closePhotoModal();
  }
});
