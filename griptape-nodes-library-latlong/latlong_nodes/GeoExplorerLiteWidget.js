/**
 * GeoExplorerLiteWidget - stable iframe-based satellite/photo viewer.
 */
export default function GeoExplorerLiteWidget(container, props) {
  const { value, onChange, disabled, height } = props;

  function readValue(raw) {
    if (!raw || typeof raw !== "object") {
      return { mode: "satellite", query: "", url: "", node_version: "", capture_nonce: "" };
    }
    return {
      mode: (raw.mode || "satellite").toLowerCase(),
      query: String(raw.query || "").trim(),
      url: String(raw.url || "").trim(),
      satellite_url: String(raw.satellite_url || "").trim(),
      photo_url: String(raw.photo_url || "").trim(),
      node_version: String(raw.node_version || "").trim(),
      capture_nonce: String(raw.capture_nonce || "").trim(),
    };
  }

  function normMode(mode) {
    return mode === "photo" ? "photo" : "satellite";
  }

  function buildClientUrl(query, mode) {
    const q = String(query || "").trim();
    const value = q || "0,0";
    const encoded = encodeURIComponent(value);
    if (mode === "photo") {
      return `https://maps.google.com/maps?q=${encoded}&z=18&output=embed`;
    }
    return `https://maps.google.com/maps?q=${encoded}&t=k&z=15&output=embed`;
  }

  const initial = readValue(value);
  const frameH = Math.max(260, Math.min(620, (height || 520) - 90));
  const initialUrl = initial.url || buildClientUrl(initial.query, normMode(initial.mode));

  if (container.__geoLite && container.__geoLite.root) {
    const st = container.__geoLite;
    st.onChange = onChange;
    st.latest = initial;
    st.queryInput.value = initial.query || st.queryInput.value || "";
    st.modeSel.value = normMode(initial.mode || st.modeSel.value);
    if (st.verEl) st.verEl.textContent = initial.node_version ? `Node ${initial.node_version}` : "";
    if (initial.url && initial.url !== st.currentUrl) {
      st.loadUrl(initial.url, false, true);
    }
    return st.cleanup;
  }

  container.innerHTML =
    '<div class="geo-lite" style="display:flex;flex-direction:column;gap:6px;padding:6px;background:#101010;border-radius:6px;">' +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        `<input class="q" value="${initial.query || ""}" placeholder="Place or lat,lng" style="flex:1;padding:6px 8px;background:#1d1d1d;border:1px solid #333;border-radius:4px;color:#ddd;font-size:12px;" ${disabled ? "disabled" : ""} />` +
        `<select class="m" style="padding:6px 8px;background:#1d1d1d;border:1px solid #333;border-radius:4px;color:#ddd;font-size:12px;" ${disabled ? "disabled" : ""}>` +
          '<option value="satellite">Satellite</option>' +
          '<option value="photo">Photo View</option>' +
        '</select>' +
        `<button class="go" style="padding:6px 10px;background:#1a4b8a;border:1px solid #2a6bba;border-radius:4px;color:#fff;font-size:12px;" ${disabled ? "disabled" : ""}>Go</button>` +
        `<button class="cap" style="padding:6px 10px;background:#2f6f5f;border:1px solid #4e9c86;border-radius:4px;color:#fff;font-size:12px;" ${disabled ? "disabled" : ""}>Capture</button>` +
      '</div>' +
      `<div class="frame-wrap" style="height:${frameH}px;border-radius:6px;overflow:hidden;background:#0b0b0b;">` +
        `<iframe class="frame" src="${initialUrl}" style="width:100%;height:100%;border:none;" allowfullscreen></iframe>` +
      '</div>' +
      '<div style="font-size:11px;color:#8a8a8a;">Satellite + Photo View (Pegman in map). <span class="ver" style="color:#6fb1ff;"></span></div>' +
    '</div>';

  const root = container.querySelector(".geo-lite");
  const queryInput = container.querySelector(".q");
  const modeSel = container.querySelector(".m");
  const goBtn = container.querySelector(".go");
  const capBtn = container.querySelector(".cap");
  const frame = container.querySelector(".frame");
  const verEl = container.querySelector(".ver");
  modeSel.value = normMode(initial.mode);
  if (verEl) verEl.textContent = initial.node_version ? `Node ${initial.node_version}` : "";
  let currentUrl = initialUrl;
  let currentOnChange = onChange;

  function loadUrl(url, emit = true, force = false) {
    if (!url) return;
    if (!force && currentUrl === url) return;
    currentUrl = url;
    frame.src = url;
    if (emit && currentOnChange) {
      currentOnChange({ mode: modeSel.value, query: queryInput.value || "", url, capture_nonce: initial.capture_nonce || "" });
    }
  }

  function runGo(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const next = buildClientUrl(queryInput.value || "", normMode(modeSel.value));
    loadUrl(next, true, true);
  }

  function runCapture(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const nonce = String(Date.now());
    if (currentOnChange) {
      currentOnChange({ mode: modeSel.value, query: queryInput.value || "", url: currentUrl, capture_nonce: nonce });
    }
  }

  goBtn.addEventListener("click", runGo);
  capBtn.addEventListener("click", runCapture);
  queryInput.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") runGo(e);
  });
  modeSel.addEventListener("change", runGo);

  function cleanup() {
    goBtn.removeEventListener("click", runGo);
    capBtn.removeEventListener("click", runCapture);
    if (container.__geoLite) container.__geoLite = null;
  }

  container.__geoLite = {
    root,
    queryInput,
    modeSel,
    currentUrl,
    latest: initial,
    verEl,
    onChange: currentOnChange,
    loadUrl: function(url, emit, force) {
      currentOnChange = container.__geoLite ? container.__geoLite.onChange : currentOnChange;
      loadUrl(url, emit, force);
      if (container.__geoLite) container.__geoLite.currentUrl = currentUrl;
    },
    cleanup,
  };

  return cleanup;
}

