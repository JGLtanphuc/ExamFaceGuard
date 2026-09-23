// Logic phía Client của Sinh Viên (Làm bài thi & Nộp bài - Không còn camera realtime trong lúc thi)
document.addEventListener("DOMContentLoaded", () => {
  const timerDisplay = document.getElementById("exam-timer");
  let isExamActive = true;

  // Lấy Token xác thực từ window (Jinja), sessionStorage, hoặc localStorage
  const userToken = window.EXAM_TOKEN || sessionStorage.getItem("access_token") || localStorage.getItem("access_token") || "";

  function getAuthHeaders(extraHeaders = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...extraHeaders
    };
    if (userToken) {
      headers["Authorization"] = `Bearer ${userToken}`;
    }
    return headers;
  }

  // Cập nhật thanh tiến độ làm bài
  function updateExamProgress() {
    const totalQuestions = document.querySelectorAll(".question-card").length || 1;
    const answeredCount = document.querySelectorAll(".question-card.answered").length;
    const progressFill = document.getElementById("progress-fill");
    const progressText = document.getElementById("progress-text");

    if (progressText) {
      progressText.innerHTML = `Đã trả lời: <strong>${answeredCount}/${totalQuestions}</strong> câu`;
    }
    if (progressFill) {
      const pct = Math.round((answeredCount / totalQuestions) * 100);
      progressFill.style.width = pct + "%";
    }
  }

  // Xử lý làm bài trắc nghiệm (lưu tự động khi click chọn)
  const optionRadios = document.querySelectorAll(".option-radio");
  optionRadios.forEach(radio => {
    radio.addEventListener("change", async (e) => {
      const questionId = e.target.getAttribute("data-question-id");
      const answerChoice = e.target.value;

      // Cập nhật giao diện active cho tile được chọn
      const parentCard = document.getElementById(`question-card-${questionId}`);
      if (parentCard) {
        parentCard.querySelectorAll(".option-tile").forEach(tile => tile.classList.remove("active"));
        const selectedTile = e.target.closest(".option-tile");
        if (selectedTile) selectedTile.classList.add("active");
      }

      try {
        const res = await fetch("/student/answer", {
          method: "POST",
          headers: getAuthHeaders(),
          body: JSON.stringify({ ma_cau_hoi: parseInt(questionId), dap_an: answerChoice })
        });
        const result = await res.json();
        if (result.success) {
          if (parentCard) parentCard.classList.add("answered");
          updateExamProgress();
        }
      } catch (err) {
        console.error("Lỗi lưu câu trả lời:", err);
      }
    });
  });

  // Khởi tạo tiến độ ban đầu
  updateExamProgress();

  // Nộp bài thi
  const submitBtn = document.getElementById("btn-submit-exam");
  if (submitBtn) {
    submitBtn.addEventListener("click", async () => {
      if (!confirm("Bạn có chắc chắn muốn nộp bài thi không? Sau khi nộp bạn sẽ không thể sửa lại câu trả lời.")) {
        return;
      }

      submitBtn.disabled = true;
      submitBtn.textContent = "Đang nộp bài...";

      try {
        const res = await fetch("/student/submit", {
          method: "POST",
          headers: getAuthHeaders()
        });
        const result = await res.json();

        if (result.success) {
          isExamActive = false;
          alert(`Nộp bài thành công!\nKết quả bài thi: ${result.correct_count}/${result.total_count} câu đúng.`);
          window.location.reload();
        } else {
          alert("Lỗi nộp bài: " + result.message);
          submitBtn.disabled = false;
          submitBtn.textContent = "Nộp bài";
        }
      } catch (err) {
        console.error("Lỗi khi nộp bài:", err);
        alert("Có lỗi xảy ra khi nộp bài. Vui lòng thử lại!");
        submitBtn.disabled = false;
        submitBtn.textContent = "Nộp bài";
      }
    });
  }

  // Đếm ngược thời gian ca thi (60 phút)
  function startTimer(durationMinutes) {
    if (!timerDisplay) return;
    let timeLeft = durationMinutes * 60;
    const timerInterval = setInterval(() => {
      if (timeLeft <= 0) {
        clearInterval(timerInterval);
        timerDisplay.textContent = "00:00";
        alert("Hết giờ làm bài! Hệ thống tự động nộp bài.");
        if (submitBtn && !submitBtn.disabled) submitBtn.click();
        return;
      }
      const minutes = Math.floor(timeLeft / 60);
      const seconds = timeLeft % 60;
      timerDisplay.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
      timeLeft--;
    }, 1000);
  }

  // Tự động thông báo đăng xuất khi thí sinh đóng tab / tắt trình duyệt
  window.addEventListener("beforeunload", () => {
    if (isExamActive) {
      try {
        navigator.sendBeacon("/student/beacon-logout");
      } catch (e) {
        // ignore
      }
    }
  });

  startTimer(60);
});
