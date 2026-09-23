// Logic phía Client của Giám Thị Dashboard - Danh sách Điểm danh & Xác thực khuôn mặt Thí sinh
document.addEventListener("DOMContentLoaded", () => {
  const roomSelect = document.getElementById("select-room");
  const shiftSelect = document.getElementById("select-shift");
  const tableBody = document.getElementById("candidate-table-body");
  const sessionInfoEl = document.getElementById("session-info-title");
  const wsStatusEl = document.getElementById("ws-status");

  // KPI counters
  const totalCountEl = document.getElementById("total-count");
  const activeCountEl = document.getElementById("active-count");
  const alertCountEl = document.getElementById("alert-count");
  const submittedCountEl = document.getElementById("submitted-count");
  const absentCountEl = document.getElementById("absent-count");

  // Search & Filter buttons
  const searchInput = document.getElementById("candidate-search");
  const filterBtns = document.querySelectorAll(".filter-btn");
  const kpiCards = document.querySelectorAll(".stat-kpi-card[data-filter]");
  const pillAllCount = document.getElementById("pill-all-count");
  const pillActiveCount = document.getElementById("pill-active-count");
  const pillAlertCount = document.getElementById("pill-alert-count");
  const pillSubmittedCount = document.getElementById("pill-submitted-count");
  const pillAbsentCount = document.getElementById("pill-absent-count");

  let currentPhienThiId = window.CURRENT_SESSION_ID || null;
  let socket = null;
  let currentFilter = "all";
  let searchQuery = "";

  // 1. Khởi tạo kết nối WebSocket
  function connectWebSocket(maPhienThi) {
    if (!maPhienThi) return;

    if (socket) {
      socket.close();
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/monitoring/${maPhienThi}`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log(`[WS] Đã kết nối giám sát phiên ${maPhienThi}`);
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleRealtimeEvent(msg);
      } catch (err) {
        console.error("Lỗi parse WS message:", err);
      }
    };

    socket.onclose = () => {
      console.warn("[WS] Mất kết nối. Đang thử kết nối lại sau 3 giây...");
      setTimeout(() => {
        if (currentPhienThiId === maPhienThi) {
          connectWebSocket(maPhienThi);
        }
      }, 3000);
    };

    socket.onerror = (err) => {
      console.error("[WS] Lỗi WebSocket:", err);
    };
  }

  // 2. Xử lý sự kiện Realtime từ Server
  function handleRealtimeEvent(msg) {
    const { event, data } = msg;

    if (event === "STUDENT_LOGIN") {
      const row = document.getElementById(`row-${data.ma_sinh_vien}`);
      if (row) {
        // Cập nhật trạng thái
        row.setAttribute("data-status", "Dang xac thuc");
        const statusCell = row.querySelector("[data-label='Trạng Thái']");
        if (statusCell) {
          statusCell.innerHTML = `<span class="status-badge status-xac-thuc">⏳ Đang xác thực</span>`;
        }
      }
      updateCountsAndFilter();
    }

    else if (event === "STUDENT_VERIFIED") {
      const row = document.getElementById(`row-${data.ma_sinh_vien}`);
      if (row) {
        row.classList.remove("row-alert");
        row.setAttribute("data-status", "Dang thi");
        row.setAttribute("data-sim", data.similarity || "");
        row.setAttribute("data-img", data.image_path || "");

        // Cập nhật thời gian
        const timeCell = row.querySelector("[data-label='Thời Gian']");
        if (timeCell && data.thoi_gian) {
          timeCell.textContent = data.thoi_gian;
        }

        // Cập nhật ảnh thumbnail
        const imgCell = row.querySelector("[data-label='Ảnh Check-in']");
        if (imgCell && data.image_path) {
          const simPct = data.similarity ? (data.similarity * 100).toFixed(1) + "%" : "--";
          imgCell.innerHTML = `
            <img src="${data.image_path}" alt="Ảnh xác thực" class="snapshot-thumb" title="Bấm để xem ảnh lớn"
                 onclick="openPhotoModal('${data.ho_ten || ''}', '${data.mssv || ''}', '${data.image_path}', '${simPct}', 'Dang thi', '${data.thoi_gian || '--'}')">
          `;
        }

        // Cập nhật gauge tương đồng
        const simCell = row.querySelector("[data-label='Độ Tương Đồng']");
        if (simCell && data.similarity !== undefined) {
          const pct = Math.round(data.similarity * 100);
          const pctStr = (data.similarity * 100).toFixed(1) + "%";
          simCell.innerHTML = `
            <div class="sim-cell">
              <div class="sim-bar-track">
                <div class="sim-bar-fill" style="width: ${pct}%; background-color: var(--success);"></div>
              </div>
              <span class="sim-bar-val" style="color: var(--success);">${pctStr}</span>
            </div>
          `;
        }

        // Cập nhật trạng thái
        const statusCell = row.querySelector("[data-label='Trạng Thái']");
        if (statusCell) {
          statusCell.innerHTML = `<span class="status-badge status-dang-thi">🟢 Đang thi</span>`;
        }

        // Cập nhật nút thao tác
        const actionCell = row.querySelector("[data-label='Thao Tác']");
        if (actionCell && data.image_path) {
          const simPct = data.similarity ? (data.similarity * 100).toFixed(1) + "%" : "--";
          actionCell.innerHTML = `
            <button type="button" class="btn-inspect"
                    onclick="openPhotoModal('${data.ho_ten || ''}', '${data.mssv || ''}', '${data.image_path}', '${simPct}', 'Dang thi', '${data.thoi_gian || '--'}')">
              🔍 Xem ảnh
            </button>
          `;
        }
      }
      updateCountsAndFilter();
    }

    else if (event === "STUDENT_VERIFY_FAILED") {
      const row = document.getElementById(`row-${data.ma_sinh_vien}`);
      if (row) {
        row.classList.add("row-alert");
        row.setAttribute("data-status", "Nghi van thi ho");
        row.setAttribute("data-sim", data.similarity || "");
        row.setAttribute("data-img", data.image_path || "");

        // Cập nhật thời gian
        const timeCell = row.querySelector("[data-label='Thời Gian']");
        if (timeCell && data.thoi_gian) {
          timeCell.textContent = data.thoi_gian;
        }

        // Cập nhật ảnh thumbnail
        const imgCell = row.querySelector("[data-label='Ảnh Check-in']");
        if (imgCell && data.image_path) {
          const simPct = data.similarity ? (data.similarity * 100).toFixed(1) + "%" : "--";
          imgCell.innerHTML = `
            <img src="${data.image_path}" alt="Ảnh xác thực" class="snapshot-thumb" title="Bấm để xem ảnh lớn"
                 onclick="openPhotoModal('${data.ho_ten || ''}', '${data.mssv || ''}', '${data.image_path}', '${simPct}', 'Nghi van thi ho', '${data.thoi_gian || '--'}')">
          `;
        }

        // Cập nhật gauge tương đồng (màu đỏ)
        const simCell = row.querySelector("[data-label='Độ Tương Đồng']");
        if (simCell && data.similarity !== undefined) {
          const pct = Math.round(data.similarity * 100);
          const pctStr = (data.similarity * 100).toFixed(1) + "%";
          simCell.innerHTML = `
            <div class="sim-cell">
              <div class="sim-bar-track">
                <div class="sim-bar-fill" style="width: ${pct}%; background-color: var(--danger);"></div>
              </div>
              <span class="sim-bar-val" style="color: var(--danger);">${pctStr}</span>
            </div>
          `;
        }

        // Cập nhật trạng thái
        const statusCell = row.querySelector("[data-label='Trạng Thái']");
        if (statusCell) {
          statusCell.innerHTML = `<span class="status-badge status-nghi-van">⚠️ Nghi vấn thi hộ</span>`;
        }

        // Cập nhật nút thao tác
        const actionCell = row.querySelector("[data-label='Thao Tác']");
        if (actionCell && data.image_path) {
          const simPct = data.similarity ? (data.similarity * 100).toFixed(1) + "%" : "--";
          actionCell.innerHTML = `
            <button type="button" class="btn-inspect"
                    onclick="openPhotoModal('${data.ho_ten || ''}', '${data.mssv || ''}', '${data.image_path}', '${simPct}', 'Nghi van thi ho', '${data.thoi_gian || '--'}')">
              🔍 Xem ảnh
            </button>
          `;
        }
      }
      updateCountsAndFilter();
    }

    else if (event === "STUDENT_SUBMIT") {
      const row = document.getElementById(`row-${data.ma_sinh_vien}`);
      if (row) {
        row.setAttribute("data-status", "Da nop");
        const statusCell = row.querySelector("[data-label='Trạng Thái']");
        if (statusCell) {
          statusCell.innerHTML = `<span class="status-badge status-da-nop">📝 Đã nộp bài</span>`;
        }
      }
      updateCountsAndFilter();
    }

    else if (event === "STUDENT_LOGOUT") {
      const row = document.getElementById(`row-${data.ma_sinh_vien}`);
      if (row) {
        row.setAttribute("data-status", "Da dang xuat");
        const statusCell = row.querySelector("[data-label='Trạng Thái']");
        if (statusCell) {
          statusCell.innerHTML = `<span class="status-badge status-dang-xuat">🚪 Đã đăng xuất</span>`;
        }
      }
      updateCountsAndFilter();
    }
  }

  // 3. Tìm kiếm & Lọc Thí sinh theo Filter Pill / Search Input
  function updateCountsAndFilter() {
    const allRows = tableBody.querySelectorAll(".candidate-row");
    let totalCount = allRows.length;
    let activeCount = 0;
    let alertCount = 0;
    let submittedCount = 0;
    let absentCount = 0;
    let visibleCount = 0;

    allRows.forEach(row => {
      const status = (row.getAttribute("data-status") || "").trim();
      const name = (row.getAttribute("data-name") || "").toLowerCase();
      const mssv = (row.getAttribute("data-mssv") || "").toLowerCase();

      // Phân loại trạng thái
      if (status === "Dang thi" || status === "Dang xac thuc") {
        activeCount++;
      } else if (status === "Nghi van thi ho" || status === "Xac thuc that bai") {
        alertCount++;
      } else if (status === "Da nop" || status === "Da ket thuc") {
        submittedCount++;
      } else {
        absentCount++;
      }

      // Kiểm tra bộ lọc
      let matchesFilter = true;
      if (currentFilter === "active") {
        matchesFilter = (status === "Dang thi" || status === "Dang xac thuc");
      } else if (currentFilter === "alert") {
        matchesFilter = (status === "Nghi van thi ho" || status === "Xac thuc that bai");
      } else if (currentFilter === "submitted") {
        matchesFilter = (status === "Da nop" || status === "Da ket thuc");
      } else if (currentFilter === "absent") {
        matchesFilter = (status === "Chua dang nhap" || status === "Da dang xuat" || status === "Ngoai tuyen" || !status);
      }

      // Kiểm tra từ khóa tìm kiếm
      const matchesSearch = !searchQuery || name.includes(searchQuery) || mssv.includes(searchQuery);

      if (matchesFilter && matchesSearch) {
        visibleCount++;
        row.style.display = "";
      } else {
        row.style.display = "none";
      }
    });

    // Cập nhật số liệu trên KPI
    if (totalCountEl) totalCountEl.textContent = totalCount;
    if (activeCountEl) activeCountEl.textContent = activeCount;
    if (alertCountEl) alertCountEl.textContent = alertCount;
    if (submittedCountEl) submittedCountEl.textContent = submittedCount;
    if (absentCountEl) absentCountEl.textContent = absentCount;

    // Cập nhật số liệu trên các Filter Pills
    if (pillAllCount) pillAllCount.textContent = totalCount;
    if (pillActiveCount) pillActiveCount.textContent = activeCount;
    if (pillAlertCount) pillAlertCount.textContent = alertCount;
    if (pillSubmittedCount) pillSubmittedCount.textContent = submittedCount;
    if (pillAbsentCount) pillAbsentCount.textContent = absentCount;

    // Hiển thị dòng empty state nếu không tìm thấy
    let emptyRow = tableBody.querySelector(".empty-filter-row");
    if (visibleCount === 0 && totalCount > 0) {
      if (!emptyRow) {
        emptyRow = document.createElement("tr");
        emptyRow.className = "empty-filter-row";
        emptyRow.innerHTML = `
          <td colspan="7" style="text-align: center; padding: 2.5rem 1rem; color: var(--slate);">
            <div style="font-size: 1.8rem; margin-bottom: 0.35rem;">🔍</div>
            <strong style="color: #334155;">Không có thí sinh phù hợp</strong>
            <p style="margin: 0.25rem 0 0; font-size: 0.82rem;">Không tìm thấy thí sinh nào khớp với bộ lọc hoặc từ khóa tìm kiếm.</p>
          </td>
        `;
        tableBody.appendChild(emptyRow);
      }
      emptyRow.style.display = "";
    } else if (emptyRow) {
      emptyRow.style.display = "none";
    }
  }

  // Lắng nghe tìm kiếm
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      searchQuery = e.target.value.trim().toLowerCase();
      updateCountsAndFilter();
    });
  }

  // Lắng nghe click các Filter Buttons
  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const target = btn.getAttribute("data-filter");
      kpiCards.forEach(k => {
        if (k.getAttribute("data-filter") === target) {
          k.classList.add("active-kpi");
        } else {
          k.classList.remove("active-kpi");
        }
      });

      currentFilter = target;
      updateCountsAndFilter();
    });
  });

  // Lắng nghe click KPI cards để lọc nhanh
  kpiCards.forEach(kpi => {
    kpi.addEventListener("click", () => {
      const target = kpi.getAttribute("data-filter");
      filterBtns.forEach(b => {
        if (b.getAttribute("data-filter") === target) {
          b.classList.add("active");
        } else {
          b.classList.remove("active");
        }
      });
      kpiCards.forEach(k => k.classList.remove("active-kpi"));
      kpi.classList.add("active-kpi");

      currentFilter = target;
      updateCountsAndFilter();
    });
  });

  // 4. Xử lý chuyển đổi Phòng thi và Ca thi trên Dropdown
  async function onSessionFilterChange() {
    const roomId = roomSelect.value;
    const shiftId = shiftSelect.value;

    const roomText = roomSelect.options[roomSelect.selectedIndex] ? roomSelect.options[roomSelect.selectedIndex].text.trim() : `Phòng ${roomId}`;
    const shiftTextRaw = shiftSelect.options[shiftSelect.selectedIndex] ? shiftSelect.options[shiftSelect.selectedIndex].text.trim() : `Ca ${shiftId}`;
    const shiftText = shiftTextRaw.split("(")[0].trim();

    // Hiển thị ngay tên phòng và ca được chọn trên tiêu đề, tuyệt đối không để chữ "Không có dữ liệu"
    if (sessionInfoEl) {
      sessionInfoEl.textContent = `${roomText} • ${shiftText}`;
    }

    try {
      const res = await fetch(`/invigilator/api/session-candidates?room_id=${roomId}&shift_id=${shiftId}`);
      const result = await res.json();

      const displayRoom = result.ten_phong || roomText;
      const displayShift = result.ten_ca || shiftText;
      if (sessionInfoEl) {
        sessionInfoEl.textContent = `${displayRoom} • ${displayShift}`;
      }

      if (!result.success) {
        tableBody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align: center; padding: 3rem; color: var(--slate);">
              <div style="font-size: 2rem; margin-bottom: 0.5rem;">📋</div>
              <h3 style="margin: 0 0 0.5rem 0; color: #334155;">Chưa có sinh viên trong phiên thi này</h3>
              <p style="margin: 0; font-size: 0.88rem;">${result.message || 'Vui lòng chọn phòng thi hoặc ca thi khác.'}</p>
            </td>
          </tr>
        `;
        if (socket) {
          socket.close();
          socket = null;
        }
        updateCountsAndFilter();
        return;
      }

      currentPhienThiId = result.ma_phien_thi;
      renderTableCandidates(result.candidates);
      connectWebSocket(currentPhienThiId);

      // Cập nhật URL query params
      const url = new URL(window.location);
      url.searchParams.set("room_id", roomId);
      url.searchParams.set("shift_id", shiftId);
      window.history.pushState({}, "", url);
    } catch (err) {
      console.error("Lỗi tải danh sách thí sinh:", err);
    }
  }

  function renderTableCandidates(candidates) {
    if (!candidates || candidates.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; padding: 3rem; color: var(--slate);">
            <div style="font-size: 2rem; margin-bottom: 0.5rem;">📋</div>
            <h3 style="margin: 0 0 0.5rem 0; color: #334155;">Không có sinh viên trong phiên thi này.</h3>
          </td>
        </tr>
      `;
      updateCountsAndFilter();
      return;
    }

    tableBody.innerHTML = candidates.map(c => {
      const initial = c.ho_ten ? c.ho_ten.trim().split(' ').slice(-1)[0][0] : 'SV';
      const isAlert = c.trang_thai_thi_sinh === 'Nghi van thi ho' || c.trang_thai_thi_sinh === 'Xac thuc that bai';

      let statusBadgeHtml = '<span class="status-badge status-chua-vao">⚪ Chưa đăng nhập</span>';
      if (c.trang_thai_thi_sinh === 'Dang thi') {
        statusBadgeHtml = '<span class="status-badge status-dang-thi">🟢 Đang thi</span>';
      } else if (c.trang_thai_thi_sinh === 'Dang xac thuc') {
        statusBadgeHtml = '<span class="status-badge status-xac-thuc">⏳ Đang xác thực</span>';
      } else if (isAlert) {
        statusBadgeHtml = '<span class="status-badge status-nghi-van">⚠️ Nghi vấn thi hộ</span>';
      } else if (c.trang_thai_thi_sinh === 'Da nop') {
        statusBadgeHtml = '<span class="status-badge status-da-nop">📝 Đã nộp bài</span>';
      } else if (c.trang_thai_thi_sinh === 'Da dang xuat' || c.trang_thai_thi_sinh === 'Ngoai tuyen') {
        statusBadgeHtml = '<span class="status-badge status-dang-xuat">🚪 Đã đăng xuất</span>';
      }

      const sim = c.do_tuong_dong_xac_thuc;
      let simHtml = `
        <div class="sim-cell">
          <div class="sim-bar-track">
            <div class="sim-bar-fill" style="width: 0%; background-color: var(--slate);"></div>
          </div>
          <span class="sim-bar-val" style="color: var(--slate);">--</span>
        </div>
      `;
      if (sim !== null && sim !== undefined) {
        const pct = Math.round(sim * 100);
        const color = sim >= 0.7 ? "var(--success)" : "var(--danger)";
        simHtml = `
          <div class="sim-cell">
            <div class="sim-bar-track">
              <div class="sim-bar-fill" style="width: ${pct}%; background-color: ${color};"></div>
            </div>
            <span class="sim-bar-val" style="color: ${color};">${(sim * 100).toFixed(1)}%</span>
          </div>
        `;
      }

      const simPctStr = sim !== null && sim !== undefined ? (sim * 100).toFixed(1) + "%" : "--";

      let thumbHtml = '<span class="no-snapshot-badge">Chưa có ảnh</span>';
      let actionHtml = '<span style="color: var(--slate); font-size: 0.75rem;">--</span>';
      if (c.anh_xac_thuc) {
        thumbHtml = `
          <img src="${c.anh_xac_thuc}" alt="Ảnh xác thực" class="snapshot-thumb" title="Bấm để xem ảnh lớn"
               onclick="openPhotoModal('${c.ho_ten || ''}', '${c.mssv || ''}', '${c.anh_xac_thuc}', '${simPctStr}', '${c.trang_thai_thi_sinh}', '${c.thoi_gian_dang_nhap || '--'}')">
        `;
        actionHtml = `
          <button type="button" class="btn-inspect"
                  onclick="openPhotoModal('${c.ho_ten || ''}', '${c.mssv || ''}', '${c.anh_xac_thuc}', '${simPctStr}', '${c.trang_thai_thi_sinh}', '${c.thoi_gian_dang_nhap || '--'}')">
            🔍 Xem ảnh
          </button>
        `;
      }

      return `
        <tr id="row-${c.ma_sinh_vien}" 
            data-mssv="${c.mssv}" 
            data-name="${(c.ho_ten || '').toLowerCase()}" 
            data-status="${c.trang_thai_thi_sinh || ''}"
            data-sim="${c.do_tuong_dong_xac_thuc || ''}"
            data-img="${c.anh_xac_thuc || ''}"
            class="candidate-row ${isAlert ? 'row-alert' : ''}">
          
          <td data-label="STT" style="text-align: center; font-weight: 700; color: var(--slate);">
            ${c.stt}
          </td>

          <td data-label="Thí Sinh">
            <div class="student-profile-cell">
              <div class="student-avatar">${initial}</div>
              <div class="student-info-col">
                <span class="student-name">${c.ho_ten}</span>
                <span class="student-mssv">MSSV: ${c.mssv}</span>
              </div>
            </div>
          </td>

          <td data-label="Ảnh Check-in" style="text-align: center;">
            ${thumbHtml}
          </td>

          <td data-label="Thời Gian" style="text-align: center; font-size: 0.85rem; font-weight: 600; color: #334155;">
            ${c.thoi_gian_dang_nhap || '--'}
          </td>

          <td data-label="Độ Tương Đồng" style="text-align: center;">
            ${simHtml}
          </td>

          <td data-label="Trạng Thái" style="text-align: center;">
            ${statusBadgeHtml}
          </td>

          <td data-label="Thao Tác" style="text-align: center;">
            ${actionHtml}
          </td>
        </tr>
      `;
    }).join("");

    updateCountsAndFilter();
  }

  if (roomSelect) roomSelect.addEventListener("change", onSessionFilterChange);
  if (shiftSelect) shiftSelect.addEventListener("change", onSessionFilterChange);

  if (currentPhienThiId) {
    connectWebSocket(currentPhienThiId);
  }
  updateCountsAndFilter();
});

// 5. Global Modal Functions cho việc xem ảnh đối sánh
window.openPhotoModal = function(name, mssv, arg3, arg4, arg5, arg6, arg7) {
  const modal = document.getElementById("photo-modal");
  if (!modal) return;

  let imgUrl = arg3;
  let simText = arg4;
  let status = arg5;
  let time = arg6;

  // Nếu người gọi truyền 7 tham số (vẫn còn tham số pc ở vị trí thứ 3)
  if (arg7 !== undefined) {
    imgUrl = arg4;
    simText = arg5;
    status = arg6;
    time = arg7;
  }

  const modalImg = document.getElementById("modal-image");
  const modalName = document.getElementById("modal-student-name");
  const modalMssv = document.getElementById("modal-student-mssv");
  const modalTime = document.getElementById("modal-time");
  const modalVerdict = document.getElementById("modal-verdict");
  const modalVerdictText = document.getElementById("modal-verdict-text");
  const modalSim = document.getElementById("modal-sim-value");

  if (modalImg) modalImg.src = imgUrl || "";
  if (modalName) modalName.textContent = name || "--";
  if (modalMssv) modalMssv.textContent = mssv || "--";
  if (modalTime) modalTime.textContent = time || "--";
  if (modalSim) modalSim.textContent = simText || "--";

  const isSuccess = (status === "Dang thi" || status === "Da nop");
  if (modalVerdict && modalVerdictText) {
    if (isSuccess) {
      modalVerdict.className = "modal-verdict-box verdict-success";
      modalVerdictText.textContent = "✅ Xác thực hợp lệ (Đạt ngưỡng 70%)";
    } else {
      modalVerdict.className = "modal-verdict-box verdict-danger";
      modalVerdictText.textContent = "⚠️ Nghi vấn thi hộ (Dưới ngưỡng 70%)";
    }
  }

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
