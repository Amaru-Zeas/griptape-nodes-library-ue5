export default function Sam2PointPickerWidget(container, props) {
  var value = props.value || {};
  var onChange = props.onChange;
  var disabled = !!props.disabled;
  var widgetHeight = (props.height && props.height > 0) ? Math.max(420, props.height - 20) : 500;

  var state = {
    imageDataUrl: typeof value.imageDataUrl === "string" ? value.imageDataUrl : "",
    imageWidth: Number(value.imageWidth) || 0,
    imageHeight: Number(value.imageHeight) || 0,
    points: Array.isArray(value.points) ? value.points.slice() : [],
    activeLabel: Number(value.activeLabel) === 0 ? 0 : 1,
    statusMessage: typeof value.statusMessage === "string" ? value.statusMessage : "Load image and add points.",
  };

  container.innerHTML =
    '<div class="sam2-point-ui nodrag nowheel" style="' +
      "display:flex;flex-direction:column;gap:8px;padding:10px;" +
      "background:#1f2228;border:1px solid #3c4352;border-radius:8px;" +
      "font-family:Segoe UI, Arial, sans-serif;font-size:12px;color:#d9dfeb;" +
      "height:" + widgetHeight + "px;box-sizing:border-box;overflow:hidden;" +
    '">' +
      '<div style="display:flex;align-items:center;gap:8px;">' +
        '<button class="btn-pos" style="padding:5px 10px;border:1px solid #3f7f3f;border-radius:4px;background:' + (state.activeLabel === 1 ? "#3f7f3f" : "#2a2f33") + ';color:#eaf7ea;cursor:pointer;">+ Positive</button>' +
        '<button class="btn-neg" style="padding:5px 10px;border:1px solid #8a4a4a;border-radius:4px;background:' + (state.activeLabel === 0 ? "#8a4a4a" : "#2a2f33") + ';color:#ffecec;cursor:pointer;">- Negative</button>' +
        '<button class="btn-undo" style="padding:5px 10px;border:1px solid #555;border-radius:4px;background:#2a2f33;color:#dce3ef;cursor:pointer;">Undo</button>' +
        '<button class="btn-clear" style="padding:5px 10px;border:1px solid #555;border-radius:4px;background:#2a2f33;color:#dce3ef;cursor:pointer;">Clear</button>' +
        '<div style="margin-left:auto;color:#9eb0ca;">Points: <span class="point-count">0</span></div>' +
      "</div>" +
      '<div style="position:relative;flex:1;min-height:260px;background:#121418;border:1px solid #3a404d;border-radius:6px;overflow:hidden;">' +
        '<canvas class="sam-canvas" style="display:block;width:100%;height:100%;cursor:crosshair;"></canvas>' +
      "</div>" +
      '<div class="status" style="padding:6px 8px;background:#181b21;border:1px solid #323844;border-radius:5px;color:#aeb8cc;"></div>' +
    "</div>";

  var root = container.querySelector(".sam2-point-ui");
  var btnPos = container.querySelector(".btn-pos");
  var btnNeg = container.querySelector(".btn-neg");
  var btnUndo = container.querySelector(".btn-undo");
  var btnClear = container.querySelector(".btn-clear");
  var pointCount = container.querySelector(".point-count");
  var statusEl = container.querySelector(".status");
  var canvas = container.querySelector(".sam-canvas");
  var ctx = canvas.getContext("2d");
  var bgImage = new Image();
  var bgLoaded = false;

  function stopEvent(e) {
    e.stopPropagation();
  }

  function syncToNode() {
    if (!onChange) return;
    onChange({
      imageDataUrl: state.imageDataUrl,
      imageWidth: state.imageWidth,
      imageHeight: state.imageHeight,
      points: state.points,
      activeLabel: state.activeLabel,
      statusMessage: state.statusMessage,
    });
  }

  function resizeCanvas() {
    var rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width));
    canvas.height = Math.max(1, Math.floor(rect.height));
    redraw();
  }

  function getImageRect() {
    if (!bgLoaded || state.imageWidth <= 0 || state.imageHeight <= 0) {
      return null;
    }
    var canvasW = canvas.width;
    var canvasH = canvas.height;
    var scale = Math.min(canvasW / state.imageWidth, canvasH / state.imageHeight);
    var drawW = state.imageWidth * scale;
    var drawH = state.imageHeight * scale;
    var drawX = (canvasW - drawW) / 2;
    var drawY = (canvasH - drawH) / 2;
    return { x: drawX, y: drawY, w: drawW, h: drawH };
  }

  function redraw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#121418";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    var imageRect = getImageRect();
    if (bgLoaded && imageRect) {
      ctx.drawImage(bgImage, imageRect.x, imageRect.y, imageRect.w, imageRect.h);
      ctx.strokeStyle = "rgba(255,255,255,0.15)";
      ctx.strokeRect(imageRect.x, imageRect.y, imageRect.w, imageRect.h);

      for (var i = 0; i < state.points.length; i += 1) {
        var p = state.points[i];
        var cx = imageRect.x + (Number(p.x) / state.imageWidth) * imageRect.w;
        var cy = imageRect.y + (Number(p.y) / state.imageHeight) * imageRect.h;
        var positive = Number(p.label) > 0;
        ctx.beginPath();
        ctx.arc(cx, cy, 6, 0, Math.PI * 2);
        ctx.fillStyle = positive ? "rgba(50, 220, 90, 0.9)" : "rgba(255, 80, 80, 0.9)";
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = "rgba(0,0,0,0.75)";
        ctx.stroke();
      }
    } else {
      ctx.fillStyle = "#8f99ad";
      ctx.font = "13px Segoe UI";
      ctx.textAlign = "center";
      ctx.fillText("Run node once to load image preview", canvas.width / 2, canvas.height / 2);
    }

    pointCount.textContent = String(state.points.length);
    statusEl.textContent = state.statusMessage || "Ready.";
  }

  function setModeButtons() {
    btnPos.style.background = state.activeLabel === 1 ? "#3f7f3f" : "#2a2f33";
    btnNeg.style.background = state.activeLabel === 0 ? "#8a4a4a" : "#2a2f33";
  }

  function setStatus(message) {
    state.statusMessage = message;
    redraw();
  }

  function updateImage() {
    bgLoaded = false;
    if (!state.imageDataUrl) {
      redraw();
      return;
    }
    bgImage.onload = function () {
      bgLoaded = true;
      if (!state.imageWidth || !state.imageHeight) {
        state.imageWidth = bgImage.naturalWidth || 0;
        state.imageHeight = bgImage.naturalHeight || 0;
      }
      redraw();
    };
    bgImage.onerror = function () {
      bgLoaded = false;
      setStatus("Failed to render preview image.");
    };
    bgImage.src = state.imageDataUrl;
  }

  function canvasClick(e) {
    if (!bgLoaded || disabled) return;
    var rect = canvas.getBoundingClientRect();
    var cx = e.clientX - rect.left;
    var cy = e.clientY - rect.top;
    var imageRect = getImageRect();
    if (!imageRect) return;
    if (cx < imageRect.x || cx > imageRect.x + imageRect.w || cy < imageRect.y || cy > imageRect.y + imageRect.h) {
      return;
    }

    var ix = ((cx - imageRect.x) / imageRect.w) * state.imageWidth;
    var iy = ((cy - imageRect.y) / imageRect.h) * state.imageHeight;

    state.points.push({
      x: Math.max(0, Math.min(state.imageWidth - 1, ix)),
      y: Math.max(0, Math.min(state.imageHeight - 1, iy)),
      label: state.activeLabel,
    });
    state.statusMessage = "Point added. Run node to update mask.";
    redraw();
    syncToNode();
  }

  btnPos.addEventListener("click", function (e) {
    e.preventDefault();
    stopEvent(e);
    state.activeLabel = 1;
    setModeButtons();
    setStatus("Positive point mode.");
    syncToNode();
  });

  btnNeg.addEventListener("click", function (e) {
    e.preventDefault();
    stopEvent(e);
    state.activeLabel = 0;
    setModeButtons();
    setStatus("Negative point mode.");
    syncToNode();
  });

  btnUndo.addEventListener("click", function (e) {
    e.preventDefault();
    stopEvent(e);
    if (state.points.length > 0) {
      state.points.pop();
      setStatus("Removed last point.");
      syncToNode();
    }
    redraw();
  });

  btnClear.addEventListener("click", function (e) {
    e.preventDefault();
    stopEvent(e);
    state.points = [];
    setStatus("Cleared all points.");
    syncToNode();
  });

  canvas.addEventListener("click", function (e) {
    stopEvent(e);
    canvasClick(e);
  });

  root.addEventListener("pointerdown", stopEvent);
  root.addEventListener("mousedown", stopEvent);

  if (disabled) {
    root.style.opacity = "0.6";
    root.style.pointerEvents = "none";
  }

  setModeButtons();
  redraw();
  updateImage();
  setTimeout(resizeCanvas, 20);
  window.addEventListener("resize", resizeCanvas);

  return function cleanup() {
    window.removeEventListener("resize", resizeCanvas);
    container.innerHTML = "";
  };
}
