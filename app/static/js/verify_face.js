// Logic phía Client: Chụp ảnh & Xác thực khuôn mặt điểm danh sinh viên
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
  let currentFacingMode = "user"; // Luôn ưu tiên Camera trước (selfie)
  let isProcessing = false;

  // Lấy Auth Token
  const token =
    window.EXAM_TOKEN ||
    sessionStorage.getItem("access_token") ||
    localStorage.getItem("access_token") ||
    "";

  // Hàm nhận diện camera trước từ nhãn thiết bị
  function isFrontCamera(label) {
    if (!label) return false;
    const l = label.toLowerCase();
    return (
      l.includes("front") ||
      l.includes("user") ||
      l.includes("trước") ||
      l.includes("truoc") ||
      l.includes("facetime") ||
      l.includes("selfie")
    );
  }

  // 1. Quét danh sách Camera và tự động ưu tiên Camera trước
  async function enumerateCameras() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices)
      return;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      availableDevices = devices.filter((d) => d.kind === "videoinput");

      if (cameraSelect && availableDevices.length > 0) {
        // Sắp xếp ưu tiên Camera trước (selfie) lên đầu tiên
        availableDevices.sort((a, b) => {
          const aFront = isFrontCamera(a.label);
          const bFront = isFrontCamera(b.label);
          if (aFront && !bFront) return -1;
          if (!aFront && bFront) return 1;
          return 0;
        });

        cameraSelect.innerHTML = availableDevices
          .map((d, idx) => {
            let label = d.label || `Camera ${idx + 1}`;
            if (isFrontCamera(label)) {
              label = "Camera mặt trước (Selfie)";
            } else if (
              label.toLowerCase().includes("back") ||
              label.toLowerCase().includes("environment") ||
              label.toLowerCase().includes("sau")
            ) {
              label =
                `Camera mặt sau ${availableDevices.length > 2 ? idx + 1 : ""}`.trim();
            }
            return `<option value="${d.deviceId}">📷 ${label}</option>`;
          })
          .join("");

        // Đồng bộ chọn đúng camera đang kích hoạt
        const currentTrack = currentStream
          ? currentStream.getVideoTracks()[0]
          : null;
        const currentSettings =
          currentTrack && currentTrack.getSettings
            ? currentTrack.getSettings()
            : {};
        if (currentSettings.deviceId) {
          cameraSelect.value = currentSettings.deviceId;
        } else if (availableDevices.length > 0) {
          cameraSelect.value = availableDevices[0].deviceId;
        }
      }

      if (availableDevices.length <= 1 && btnSwitchCam) {
        btnSwitchCam.style.display = "none";
      } else if (btnSwitchCam) {
        btnSwitchCam.style.display = "flex";
      }
    } catch (err) {
      console.warn("Không thể quét thiết bị camera:", err);
    }
  }

  // 2. Khởi động Camera (Tự động mở trực tiếp Camera trước trên Mobile & Laptop)
  async function startCamera(deviceId = null, facingMode = "user") {
    if (currentStream) {
      currentStream.getTracks().forEach((track) => track.stop());
      currentStream = null;
    }

    currentFacingMode = facingMode;

    const videoConstraints = {
      width: { ideal: 640 },
      height: { ideal: 480 },
    };

    if (deviceId) {
      videoConstraints.deviceId = { exact: deviceId };
    } else {
      videoConstraints.facingMode = { ideal: facingMode };
    }

    try {
      currentStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: videoConstraints,
      });
    } catch (err) {
      console.warn("Thử fallback trực tiếp với facingMode:", facingMode, err);
      try {
        currentStream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: deviceId
            ? { deviceId: { exact: deviceId } }
            : { facingMode: facingMode },
        });
      } catch (fallbackErr) {
        try {
          currentStream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: true,
          });
        } catch (finalErr) {
          console.error("Lỗi mở camera:", finalErr);
          showFeedback(
            "error",
            "⚠️ Không thể truy cập Camera. Vui lòng cấp quyền Camera trên trình duyệt và thử lại.",
          );
          return;
        }
      }
    }

    if (!currentStream) return;

    video.srcObject = currentStream;
    video.style.display = "block";
    imgPreview.style.display = "none";
    if (faceGuide) faceGuide.style.display = "flex";

    // Cập nhật danh sách camera sau khi có quyền truy cập
    await enumerateCameras();

    // Tự động chuyển thẳng vào Camera trước nếu điện thoại mở nhầm camera sau
    if (!deviceId && availableDevices.length > 0) {
      const activeTrack = currentStream.getVideoTracks()[0];
      const activeSettings =
        activeTrack && activeTrack.getSettings ? activeTrack.getSettings() : {};
      const activeId = activeSettings.deviceId;

      const frontDevice = availableDevices.find((d) => isFrontCamera(d.label));
      if (frontDevice && activeId && frontDevice.deviceId !== activeId) {
        selectedDeviceId = frontDevice.deviceId;
        if (cameraSelect) cameraSelect.value = frontDevice.deviceId;
        await startCamera(frontDevice.deviceId, "user");
      }
    }
  }

  // 3. Hiển thị thông báo phản hồi (không hiện tên model)
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
      showFeedback(
        "error",
        "Camera chưa sẵn sàng. Vui lòng đợi trong giây lát.",
      );
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

    // Chỉ hiện "Đang xác thực...", không hiện tên model AI
    showFeedback("loading", "Đang xác thực...");

    try {
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch("/student/api/verify-face", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ image_base64: base64Image }),
      });

      let result = null;
      try {
        result = await res.json();
      } catch (e) {
        // ignore parse error
      }

      if (res.ok && result && result.success) {
        const pct = (result.similarity * 100).toFixed(1);
        showFeedback(
          "success",
          `✅ Xác thực thành công (${pct}%). Đang chuyển vào phòng thi...`,
        );

        const serverToken = (result && result.token) || token;
        let redirectUrl = (result && result.redirect_url) || "/student";
        if (serverToken && !redirectUrl.includes("token=")) {
          redirectUrl +=
            (redirectUrl.includes("?") ? "&" : "?") +
            "token=" +
            encodeURIComponent(serverToken);
        }

        if (serverToken) {
          try {
            sessionStorage.setItem("access_token", serverToken);
            localStorage.setItem("access_token", serverToken);
          } catch (e) {}
        }

        // Dừng camera và chuyển trang sau 1 giây
        setTimeout(() => {
          if (currentStream) {
            currentStream.getTracks().forEach((t) => t.stop());
          }
          window.location.href = redirectUrl;
        }, 1000);
      } else {
        const errorMsg =
          (result && (result.message || result.error || result.detail)) ||
          "Xác thực không thành công. Vui lòng chụp lại.";
        showFeedback("error", `❌ ${errorMsg}`);
        btnRetake.style.display = "flex";
        btnCapture.style.display = "none";
      }
    } catch (err) {
      console.error("Lỗi gửi xác thực:", err);
      showFeedback(
        "error",
        "❌ Lỗi kết nối mạng hoặc máy chủ. Vui lòng thử lại.",
      );
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
      const selectedOption = cameraSelect.options[cameraSelect.selectedIndex];
      const txt = (selectedOption ? selectedOption.text : "").toLowerCase();
      if (txt.includes("sau") || txt.includes("back")) {
        currentFacingMode = "environment";
      } else {
        currentFacingMode = "user";
      }
      startCamera(selectedDeviceId, currentFacingMode);
    });
  }

  if (btnSwitchCam) {
    btnSwitchCam.addEventListener("click", async () => {
      // Đổi qua lại giữa camera trước và sau
      currentFacingMode = currentFacingMode === "user" ? "environment" : "user";

      let targetDev = null;
      if (currentFacingMode === "user") {
        targetDev = availableDevices.find((d) => isFrontCamera(d.label));
      } else {
        targetDev = availableDevices.find((d) => {
          const l = (d.label || "").toLowerCase();
          return (
            l.includes("back") || l.includes("environment") || l.includes("sau")
          );
        });
      }

      if (targetDev) {
        selectedDeviceId = targetDev.deviceId;
        if (cameraSelect) cameraSelect.value = selectedDeviceId;
        await startCamera(selectedDeviceId, currentFacingMode);
      } else {
        await startCamera(null, currentFacingMode);
      }
    });
  }

  // Gắn sự kiện các nút chính
  if (btnCapture) btnCapture.addEventListener("click", handleVerifyClick);
  if (btnRetake) btnRetake.addEventListener("click", handleRetakeClick);

  // Bắt đầu mở trực tiếp Camera trước
  startCamera();
});
