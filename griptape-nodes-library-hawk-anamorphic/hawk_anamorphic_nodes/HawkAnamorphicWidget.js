export default function HawkAnamorphicWidget(container, props) {
  var value = props.value;
  var onChange = props.onChange;
  var disabled = !!props.disabled;
  var widgetHeight = (props.height && props.height > 0) ? Math.max(430, props.height - 20) : 520;

  var state = {
    inputImagePath: "",
    outputImagePath: "",
    method: "distort",
    lensMm: "45",
    focusM: 12.0,
    useGpuIfAvailable: false,
    chromaticAberration: 0.70,
    disableChromaticAberration: false,
    vignette: 0.45,
    disableVignette: false,
    edgeSoftness: 0.65,
    disableEdgeSoftness: false,
    maskScaleW: 1.0,
    maskScaleH: 1.0,
    breathingStrength: 1.0,
    disableAll: false,
    statusMessage: "Ready.",
    profileUsed: {}
  };

  if (value && typeof value === "object") {
    if (value.inputImagePath !== undefined) state.inputImagePath = String(value.inputImagePath || "");
    if (value.outputImagePath !== undefined) state.outputImagePath = String(value.outputImagePath || "");
    if (value.method !== undefined) state.method = normalizeMethod(value.method);
    if (value.lensMm !== undefined) state.lensMm = String(value.lensMm || "45");
    if (value.focusM !== undefined) state.focusM = Number(value.focusM) || 12.0;
    if (value.useGpuIfAvailable !== undefined) state.useGpuIfAvailable = !!value.useGpuIfAvailable;
    if (value.chromaticAberration !== undefined) state.chromaticAberration = Number(value.chromaticAberration) || 0.70;
    if (value.disableChromaticAberration !== undefined) state.disableChromaticAberration = !!value.disableChromaticAberration;
    if (value.vignette !== undefined) state.vignette = Number(value.vignette) || 0.45;
    if (value.disableVignette !== undefined) state.disableVignette = !!value.disableVignette;
    if (value.edgeSoftness !== undefined) state.edgeSoftness = Number(value.edgeSoftness) || 0.65;
    if (value.disableEdgeSoftness !== undefined) state.disableEdgeSoftness = !!value.disableEdgeSoftness;
    if (value.maskScaleW !== undefined) state.maskScaleW = Number(value.maskScaleW) || 1.0;
    if (value.maskScaleH !== undefined) state.maskScaleH = Number(value.maskScaleH) || 1.0;
    if (value.breathingStrength !== undefined) state.breathingStrength = Number(value.breathingStrength) || 1.0;
    if (value.disableAll !== undefined) state.disableAll = !!value.disableAll;
    if (value.statusMessage !== undefined) state.statusMessage = String(value.statusMessage || "");
    if (value.profileUsed && typeof value.profileUsed === "object") state.profileUsed = value.profileUsed;
  }

  container.innerHTML =
    '<div class="hawk-ui nodrag nowheel" style="' +
      "display:flex;flex-direction:column;gap:8px;" +
      "padding:10px;background:#2b2b2b;border:1px solid #474747;border-radius:8px;" +
      "font-family:Segoe UI, Arial, sans-serif;font-size:12px;color:#d7d7d7;" +
      "width:100%;height:" + widgetHeight + "px;box-sizing:border-box;overflow:hidden;" +
    '">' +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:52px;color:#bcbcbc;">Input</span>' +
        '<input class="inp-input" type="text" value="' + esc(state.inputImagePath) + '" placeholder="A:/path/to/source.png" style="' + textInputStyle() + ';flex:1;" />' +
      "</div>" +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:52px;color:#bcbcbc;">Output</span>' +
        '<input class="inp-output" type="text" value="' + esc(state.outputImagePath) + '" placeholder="optional (auto if blank)" style="' + textInputStyle() + ';flex:1;" />' +
      "</div>" +

      '<div style="border-top:1px solid #3f3f3f;padding-top:8px;">' +
        '<div style="margin-bottom:6px;color:#cfcfcf;font-weight:600;">Method:</div>' +
        '<div style="display:flex;gap:6px;">' +
          methodBtn("distort", "Distort", state.method) +
          methodBtn("undistort", "Undistort", state.method) +
          methodBtn("off", "Turn off", state.method) +
        "</div>" +
      "</div>" +

      '<div style="border-top:1px solid #3f3f3f;padding-top:8px;">' +
        '<div style="margin-bottom:6px;color:#cfcfcf;font-weight:600;">Focal Length:</div>' +
        '<div style="display:flex;gap:5px;flex-wrap:wrap;">' +
          lensBtn("28", state.lensMm) +
          lensBtn("35", state.lensMm) +
          lensBtn("45", state.lensMm) +
          lensBtn("55", state.lensMm) +
          lensBtn("65", state.lensMm) +
          lensBtn("80", state.lensMm) +
          lensBtn("110", state.lensMm) +
        "</div>" +
      "</div>" +

      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:92px;color:#cfcfcf;">Focus (meter):</span>' +
        '<input class="inp-focus-num" type="number" min="1" max="100" step="0.1" value="' + fixed(state.focusM, 1) + '" style="width:74px;' + textInputStyle() + '" />' +
        '<input class="inp-focus-slider" type="range" min="1" max="100" step="0.1" value="' + fixed(state.focusM, 1) + '" style="flex:1;" />' +
      "</div>" +

      '<details class="extra-settings" open style="border-top:1px solid #3f3f3f;padding-top:8px;">' +
        '<summary style="cursor:pointer;color:#cfcfcf;font-weight:600;list-style:none;">Extra settings</summary>' +
        '<div style="margin-top:7px;display:flex;flex-direction:column;gap:6px;">' +
          '<label style="display:flex;align-items:center;gap:7px;color:#cfcfcf;">' +
            '<input class="chk-gpu" type="checkbox" ' + (state.useGpuIfAvailable ? "checked" : "") + " /> Use GPU if available" +
          "</label>" +
          effectRow("Chromatic Aberration Level", "ca", state.chromaticAberration, state.disableChromaticAberration) +
          effectRow("Vignette", "vig", state.vignette, state.disableVignette) +
          effectRow("Edge's blur", "edge", state.edgeSoftness, state.disableEdgeSoftness) +
          '<div style="display:flex;gap:6px;align-items:center;">' +
            '<span style="width:170px;color:#bcbcbc;">Mask transform w / h</span>' +
            '<input class="inp-mask-w" type="number" min="0.25" max="4" step="0.01" value="' + fixed(state.maskScaleW, 2) + '" style="width:72px;' + textInputStyle() + '" />' +
            '<input class="inp-mask-h" type="number" min="0.25" max="4" step="0.01" value="' + fixed(state.maskScaleH, 2) + '" style="width:72px;' + textInputStyle() + '" />' +
          "</div>" +
          '<div style="display:flex;gap:6px;align-items:center;">' +
            '<span style="width:170px;color:#bcbcbc;">Breathing strength</span>' +
            '<input class="sl-breath" type="range" min="0" max="2" step="0.01" value="' + fixed(state.breathingStrength, 2) + '" style="flex:1;" />' +
            '<span class="sl-breath-val" style="width:38px;text-align:right;color:#ededed;">' + fixed(state.breathingStrength, 2) + "</span>" +
          "</div>" +
          '<label style="display:flex;align-items:center;gap:7px;color:#efefef;font-weight:600;">' +
            '<input class="chk-disable-all" type="checkbox" ' + (state.disableAll ? "checked" : "") + " /> Disable All" +
          "</label>" +
        "</div>" +
      "</details>" +

      '<div class="txt-profile" style="padding:7px 8px;background:#232323;border:1px solid #444;border-radius:5px;color:#e3e3e3;"></div>' +
      '<div class="txt-status" style="padding:7px 8px;background:#1f1f1f;border:1px solid #3d3d3d;border-radius:5px;color:#bfc8e7;"></div>' +
    "</div>";

  var root = container.querySelector(".hawk-ui");
  var inpInput = container.querySelector(".inp-input");
  var inpOutput = container.querySelector(".inp-output");
  var inpFocusNum = container.querySelector(".inp-focus-num");
  var inpFocusSlider = container.querySelector(".inp-focus-slider");
  var chkGpu = container.querySelector(".chk-gpu");
  var slCa = container.querySelector(".sl-ca");
  var slVig = container.querySelector(".sl-vig");
  var slEdge = container.querySelector(".sl-edge");
  var chkDisableCa = container.querySelector(".chk-disable-ca");
  var chkDisableVig = container.querySelector(".chk-disable-vig");
  var chkDisableEdge = container.querySelector(".chk-disable-edge");
  var inpMaskW = container.querySelector(".inp-mask-w");
  var inpMaskH = container.querySelector(".inp-mask-h");
  var slBreath = container.querySelector(".sl-breath");
  var chkDisableAll = container.querySelector(".chk-disable-all");
  var txtProfile = container.querySelector(".txt-profile");
  var txtStatus = container.querySelector(".txt-status");
  var methodButtons = container.querySelectorAll(".btn-method");
  var lensButtons = container.querySelectorAll(".btn-lens");

  function normalizeMethod(value) {
    var v = String(value || "distort").toLowerCase();
    return (v === "distort" || v === "undistort" || v === "off") ? v : "distort";
  }

  function esc(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function fixed(v, digits) {
    return Number(v || 0).toFixed(digits);
  }

  function textInputStyle() {
    return "padding:4px 6px;background:#1f1f1f;border:1px solid #505050;border-radius:4px;color:#e4e4e4;outline:none";
  }

  function baseButtonStyle(active) {
    if (active) {
      return "padding:4px 10px;border:1px solid #7f7f7f;border-radius:4px;background:#5b5b5b;color:#fff;font-weight:600;cursor:pointer";
    }
    return "padding:4px 10px;border:1px solid #555;border-radius:4px;background:#393939;color:#d8d8d8;cursor:pointer";
  }

  function methodBtn(key, label, activeKey) {
    return '<button class="btn-method" data-method="' + key + '" style="' + baseButtonStyle(key === activeKey) + '">' + label + "</button>";
  }

  function lensBtn(key, activeKey) {
    return '<button class="btn-lens" data-lens="' + key + '" style="' + baseButtonStyle(key === activeKey) + ';min-width:54px;">' + key + "mm</button>";
  }

  function effectRow(label, cls, valueNum, disabledFlag) {
    return (
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:170px;color:#bcbcbc;">' + label + "</span>" +
        '<input class="sl-' + cls + '" type="range" min="0" max="2" step="0.01" value="' + fixed(valueNum, 2) + '" style="flex:1;" />' +
        '<span class="sl-' + cls + '-val" style="width:38px;text-align:right;color:#ededed;">' + fixed(valueNum, 2) + "</span>" +
        '<label style="display:flex;align-items:center;gap:4px;color:#bbbbbb;">' +
          '<input class="chk-disable-' + cls + '" type="checkbox" ' + (disabledFlag ? "checked" : "") + " /> disable" +
        "</label>" +
      "</div>"
    );
  }

  function setSliderLabel(slider, digits) {
    var label = container.querySelector("." + slider.className + "-val");
    if (label) label.textContent = fixed(slider.value, digits);
  }

  function readInputs() {
    state.inputImagePath = (inpInput.value || "").trim();
    state.outputImagePath = (inpOutput.value || "").trim();
    state.focusM = Number(inpFocusNum.value) || 12.0;
    state.useGpuIfAvailable = !!chkGpu.checked;
    state.chromaticAberration = Number(slCa.value) || 0.70;
    state.disableChromaticAberration = !!chkDisableCa.checked;
    state.vignette = Number(slVig.value) || 0.45;
    state.disableVignette = !!chkDisableVig.checked;
    state.edgeSoftness = Number(slEdge.value) || 0.65;
    state.disableEdgeSoftness = !!chkDisableEdge.checked;
    state.maskScaleW = Number(inpMaskW.value) || 1.0;
    state.maskScaleH = Number(inpMaskH.value) || 1.0;
    state.breathingStrength = Number(slBreath.value) || 1.0;
    state.disableAll = !!chkDisableAll.checked;
  }

  function syncToNode() {
    if (!onChange) return;
    onChange({
      inputImagePath: state.inputImagePath,
      outputImagePath: state.outputImagePath,
      method: state.method,
      lensMm: state.lensMm,
      focusM: state.focusM,
      useGpuIfAvailable: state.useGpuIfAvailable,
      chromaticAberration: state.chromaticAberration,
      disableChromaticAberration: state.disableChromaticAberration,
      edgeSoftness: state.edgeSoftness,
      disableEdgeSoftness: state.disableEdgeSoftness,
      maskScaleW: state.maskScaleW,
      maskScaleH: state.maskScaleH,
      vignette: state.vignette,
      disableVignette: state.disableVignette,
      breathingStrength: state.breathingStrength,
      disableAll: state.disableAll,
      statusMessage: state.statusMessage,
      profileUsed: state.profileUsed
    });
  }

  function refreshButtonStates() {
    for (var i = 0; i < methodButtons.length; i += 1) {
      var btnM = methodButtons[i];
      var m = btnM.getAttribute("data-method");
      btnM.style.cssText = baseButtonStyle(m === state.method);
    }
    for (var j = 0; j < lensButtons.length; j += 1) {
      var btnL = lensButtons[j];
      var l = btnL.getAttribute("data-lens");
      btnL.style.cssText = baseButtonStyle(l === state.lensMm) + ";min-width:54px;";
    }
  }

  function setReadback() {
    var p = state.profileUsed || {};
    var methodTitle = (state.method === "off") ? "Turn off" : (state.method === "undistort" ? "Undistort" : "Distort");
    var lens = (p.lens_mm ? p.lens_mm : state.lensMm) + "mm";
    var zoom = (p.zoom_factor !== undefined) ? ("zoom " + fixed(p.zoom_factor, 3)) : "zoom pending";
    var ca = (p.chromatic_shift_px !== undefined) ? ("CA " + p.chromatic_shift_px + "px") : "CA pending";
    txtProfile.textContent = methodTitle + " | " + lens + " | " + zoom + " | " + ca;

    txtStatus.textContent = state.statusMessage || "Ready.";
    txtStatus.style.color = /failed|required|not found|error/i.test(txtStatus.textContent) ? "#ff9aa9" : "#bfc8e7";
  }

  function syncFocusPair(fromSlider) {
    if (fromSlider) {
      inpFocusNum.value = fixed(inpFocusSlider.value, 1);
    } else {
      inpFocusSlider.value = String(inpFocusNum.value || "12.0");
    }
  }

  function stop(e) { e.stopPropagation(); }

  function bindInput(element, onInputExtra) {
    element.addEventListener("keydown", stop);
    element.addEventListener("keyup", stop);
    element.addEventListener("input", function (e) {
      stop(e);
      if (onInputExtra) onInputExtra();
      readInputs();
      setReadback();
      syncToNode();
    });
    element.addEventListener("change", function (e) {
      stop(e);
      if (onInputExtra) onInputExtra();
      readInputs();
      setReadback();
      syncToNode();
    });
  }

  if (disabled) {
    root.style.opacity = "0.65";
    root.style.pointerEvents = "none";
  }

  for (var mb = 0; mb < methodButtons.length; mb += 1) {
    methodButtons[mb].addEventListener("click", function (e) {
      e.preventDefault();
      stop(e);
      state.method = normalizeMethod(this.getAttribute("data-method"));
      refreshButtonStates();
      setReadback();
      syncToNode();
    });
  }
  for (var lb = 0; lb < lensButtons.length; lb += 1) {
    lensButtons[lb].addEventListener("click", function (e) {
      e.preventDefault();
      stop(e);
      state.lensMm = String(this.getAttribute("data-lens") || "45");
      refreshButtonStates();
      setReadback();
      syncToNode();
    });
  }

  bindInput(inpInput);
  bindInput(inpOutput);
  bindInput(inpFocusNum, function () { syncFocusPair(false); });
  bindInput(inpFocusSlider, function () { syncFocusPair(true); });
  bindInput(chkGpu);
  bindInput(slCa, function () { setSliderLabel(slCa, 2); });
  bindInput(slVig, function () { setSliderLabel(slVig, 2); });
  bindInput(slEdge, function () { setSliderLabel(slEdge, 2); });
  bindInput(chkDisableCa);
  bindInput(chkDisableVig);
  bindInput(chkDisableEdge);
  bindInput(inpMaskW);
  bindInput(inpMaskH);
  bindInput(slBreath, function () { setSliderLabel(slBreath, 2); });
  bindInput(chkDisableAll);

  setSliderLabel(slCa, 2);
  setSliderLabel(slVig, 2);
  setSliderLabel(slEdge, 2);
  setSliderLabel(slBreath, 2);
  refreshButtonStates();
  setReadback();

  root.addEventListener("pointerdown", stop);
  root.addEventListener("mousedown", stop);

  return function cleanup() {
    container.innerHTML = "";
  };
}
