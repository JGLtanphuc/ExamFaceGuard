// Logic phía Client: Chụp ảnh & Xác thực khuôn mặt điểm danh sinh viên (RetinaFace + FaceNet512)
document.addEventListener("DOMContentLoaded", () => {
  const video = document.getElementById("video-feed");
  const imgPreview = document.getElementById("captured-image-preview");
  const canvas = document.getElementById("capture-canvas");
  const faceGuide = document.getElementById("face-guide");
  const cameraSelect = document.getElementById("camera-select");
  const btnSwitchCam = document.getElementById("btn-switch-cam");
  const btnCapture = document.getElementById("btn-capture");
  const btnRetake = document.getElementById("btn-retake");
  const feedbackBox = document.getElementById("status-feedback");

  let currentStream = null;
  let availableDevices = [];
  let selectedDeviceId = null;
  let currentFacingMode = "user"; // Mặc định camera trước
  let isProcessing = false;

  // Lấy Auth Token
  const token = window.EXAM_TOKEN || sessionStorage.getItem("access_token") || localStorage.getItem("access_token") || "";

  // 1. Quét danh sách Camera
  async function enumerateCameras() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      availableDevices = devices.filter(d => d.kind === "videoinput");

      if (cameraSelect && availableDevices.length > 0) {
        cameraSelect.innerHTML = availableDevices.map((d, idx) => {
          const label = d.label || `Camera ${idx + 1}`;
          return `<option value="${d.deviceId}">📷 ${label}</option>`;
        }).join("");
      }

      if (availableDevices.length <= 1 && btnSwitchCam) {
        btnSwitchCam.style.display = "none";
      }
    } catch (err) {
      console.warn("Không thể quét thiết bị camera:", err);
    }
  }

  // 2. Khởi động Camera
  async function startCamera(deviceId = null, facingMode = "user") {
    if (currentStream) {
      currentStream.getTracks().forEach(track => track.stop());
    }

    const constraints = {
      audio: false,
      video: deviceId
        ? { deviceId: { exact: deviceId } }
        : {
            facingMode: facingMode,
            width: { ideal: 640 },
            height: { ideal: 480 }
          }
    };

    try {
      currentStream = await navigator.mediaDevices.getUserMedia(constraints);
      video.srcObject = currentStream;
      video.style.display = "block";
      imgPreview.style.display = "none";
      if (faceGuide) faceGuide.style.display = "flex";

      // Sau khi được cấp quyền, quét lại danh sách thiết bị có label
      if (availableDevices.length === 0 || !availableDevices[0].label) {
        await enumerateCameras();
      }
    } catch (err) {
      console.error("Lỗi mở camera:", err);
      showFeedback("error", "⚠️ Không thể truy cập Camera. Vui lòng cấp quyền Camera trên trình duyệt và thử lại.");
    }
  }

  // 3. Hiển thị thông báo phản hồi
  function showFeedback(type, message) {
    if (!feedbackBox) return;
    feedbackBox.className = `status-feedback-box ${type}`;
    if (type === "loading") {
      feedbackBox.innerHTML = `<div class="spinner"></div><span>${message}</span>`;
    } else {
      feedbackBox.innerHTML = `<span>${message}</span>`;
    }
    feedbackBox.style.display = type === "loading" ? "flex" : "block";
  }

  function hideFeedback() {
    if (feedbackBox) feedbackBox.style.display = "none";
  }

  // 4. Chụp ảnh từ Camera feed
  function capturePhoto() {
    if (!video || video.readyState < 2) {
      showFeedback("error", "Camera chưa sẵn sàng. Vui lòng đợi trong giây lát.");
      return null;
    }

    const vw = video.videoWidth || 640;
    const vh = video.videoHeight || 480;

    canvas.width = vw;
    canvas.height = vh;
    const ctx = canvas.getContext("2d");

    // Nếu là camera trước, lật ảnh lại cho tự nhiên đúng chiều thực
    if (currentFacingMode === "user") {
      ctx.translate(vw, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(video, 0, 0, vw, vh);

    // Xuất ảnh JPEG chất lượng cao 0.85
    const base64Data = canvas.toDataURL("image/jpeg", 0.85);

    // Hiển thị ảnh chụp tĩnh lên viewport
    imgPreview.src = base64Data;
    imgPreview.style.display = "block";
    video.style.display = "none";
    if (faceGuide) faceGuide.style.display = "none";

    return base64Data;
  }

  // 5. Gửi yêu cầu Xác thực khuôn mặt lên Backend
  async function handleVerifyClick() {
    if (isProcessing) return;

    const base64Image = capturePhoto();
    if (!base64Image) return;

    isProcessing = true;
    btnCapture.disabled = true;
    btnCapture.innerHTML = `<span>⏳ Đang xác thực...</span>`;
    btnRetake.style.display = "none";

    showFeedback("loading", "Đang nhận diện và đối sánh khuôn mặt bằng RetinaFace + FaceNet512...");

    try {
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch("/student/api/verify-face", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ image_base64: base64Image })
      });

      let result = null;
      try {
        result = await res.json();
      } catch (e) {
        // ignore parse error
      }

      if (res.ok && result && result.success) {
        const pct = (result.similarity * 100).toFixed(1);
        showFeedback("success", `✅ Xác thực thành công (${pct}%). Đang chuyển vào phòng thi...`);

        // Dừng camera và chuyển trang sau 1 giây
        setTimeout(() => {
          if (currentStream) {
            currentStream.getTracks().forEach(t => t.stop());
          }
          window.location.href = result.redirect_url || "/student";
        }, 1000);
      } else {
        const errorMsg = (result && (result.message || result.error || result.detail)) || "Xác thực không thành công. Vui lòng chụp lại.";
        showFeedback("error", `❌ ${errorMsg}`);
        btnRetake.style.display = "flex";
        btnCapture.style.display = "none";
      }
    } catch (err) {
      console.error("Lỗi gửi xác thực:", err);
      showFeedback("error", "❌ Lỗi kết nối mạng hoặc máy chủ. Vui lòng thử lại.");
      btnRetake.style.display = "flex";
      btnCapture.style.display = "none";
    } finally {
      isProcessing = false;
      btnCapture.disabled = false;
      btnCapture.innerHTML = `<span>Xác Thực</span>`;
    }
  }

  // 6. Xử lý Chụp lại
  function handleRetakeClick() {
    imgPreview.style.display = "none";
    video.style.display = "block";
    if (faceGuide) faceGuide.style.display = "flex";

    btnCapture.style.display = "flex";
    btnRetake.style.display = "none";
    hideFeedback();
  }

  // 7. Chuyển đổi camera
  if (cameraSelect) {
    cameraSelect.addEventListener("change", (e) => {
      selectedDeviceId = e.target.value;
      startCamera(selectedDeviceId);
    });
  }

  if (btnSwitchCam) {
    btnSwitchCam.addEventListener("click", () => {
      currentFacingMode = currentFacingMode === "user" ? "environment" : "user";
      startCamera(null, currentFacingMode);
    });
  }

  // Gắn sự kiện các nút chính
  if (btnCapture) btnCapture.addEventListener("click", handleVerifyClick);
  if (btnRetake) btnRetake.addEventListener("click", handleRetakeClick);

  // Bắt đầu
  startCamera();
});

