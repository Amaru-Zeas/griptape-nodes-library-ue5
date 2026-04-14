/**
 * Image360ViewerWidget
 * Minimal equirectangular viewer with mouse drag + wheel zoom.
 */

let pannellumLoadPromise = null;

function loadPannellum() {
  if (window.pannellum) return Promise.resolve(window.pannellum);
  if (pannellumLoadPromise) return pannellumLoadPromise;

  pannellumLoadPromise = new Promise((resolve, reject) => {
    const cssId = "gtn-pannellum-css";
    if (!document.getElementById(cssId)) {
      const link = document.createElement("link");
      link.id = cssId;
      link.rel = "stylesheet";
      link.href = "https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css";
      document.head.appendChild(link);
    }

    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js";
    script.async = true;
    script.onload = () => resolve(window.pannellum);
    script.onerror = () => reject(new Error("Failed to load pannellum assets."));
    document.body.appendChild(script);
  });

  return pannellumLoadPromise;
}

function normalizeValue(raw) {
  if (!raw) return { image_url: "", image_data_url: "", hfov: 95 };
  if (typeof raw === "string") return { image_url: raw, image_data_url: "", hfov: 95 };
  return {
    image_url: String(raw.image_url || "").trim(),
    image_data_url: String(raw.image_data_url || "").trim(),
    hfov: Number.isFinite(Number(raw.hfov)) ? Number(raw.hfov) : 95,
  };
}

function normalizePanoramaSource(imageUrl, imageDataUrl) {
  const dataUrl = String(imageDataUrl || "").trim();
  if (dataUrl) return dataUrl;

  const raw = String(imageUrl || "").trim();
  if (!raw) return "";
  if (raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("data:")) return raw;
  if (raw.startsWith("/")) return window.location.origin + raw;
  return raw;
}

export default function Image360ViewerWidget(container, props) {
  const { value, height } = props;
  const state = normalizeValue(value);
  const frameHeight = Math.max(320, Number(height || 680) - 170);

  if (!container.__image360Widget) {
    container.innerHTML =
      '<div class="nodrag" style="display:flex;flex-direction:column;gap:8px;padding:6px;background:#101010;border-radius:6px;">' +
        `<div class="viewer-host" style="width:100%;height:${frameHeight}px;background:#000;border-radius:6px;overflow:hidden;"></div>` +
        '<div class="viewer-note" style="font-size:11px;color:#8a8a8a;">Drag: rotate | Wheel: zoom | Shift+drag: pan</div>' +
      "</div>";

    const host = container.querySelector(".viewer-host");
    container.__image360Widget = {
      host,
      viewer: null,
      imageUrl: "",
      cleanup: () => {
        const st = container.__image360Widget;
        if (st && st.viewer && typeof st.viewer.destroy === "function") {
          try {
            st.viewer.destroy();
          } catch (err) {
            // no-op
          }
        }
        container.__image360Widget = null;
      },
    };
  } else {
    const host = container.__image360Widget.host;
    if (host) host.style.height = `${frameHeight}px`;
  }

  const st = container.__image360Widget;
  if (!st || !st.host) {
    return function cleanup() {};
  }

  function renderMessage(text) {
    st.host.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#777;font-size:12px;text-align:center;padding:12px;">' +
      text +
      "</div>";
  }

  function renderViewer(imageUrl, imageDataUrl, hfov) {
    const panoramaSource = normalizePanoramaSource(imageUrl, imageDataUrl);
    if (!panoramaSource) {
      if (st.viewer && typeof st.viewer.destroy === "function") {
        try {
          st.viewer.destroy();
        } catch (err) {
          // no-op
        }
      }
      st.viewer = null;
      st.imageUrl = "";
      renderMessage("Connect an image and run the node.");
      return;
    }

    if (st.viewer && st.imageUrl === panoramaSource) {
      try {
        st.viewer.setHfov(Math.max(40, Math.min(140, Number(hfov) || 95)));
      } catch (err) {
        // no-op
      }
      return;
    }

    if (st.viewer && typeof st.viewer.destroy === "function") {
      try {
        st.viewer.destroy();
      } catch (err) {
        // no-op
      }
      st.viewer = null;
    }

    st.host.innerHTML = "";
    st.imageUrl = panoramaSource;
    st.viewer = window.pannellum.viewer(st.host, {
      type: "equirectangular",
      panorama: panoramaSource,
      autoLoad: true,
      showControls: true,
      mouseZoom: true,
      draggable: true,
      compass: false,
      hfov: Math.max(40, Math.min(140, Number(hfov) || 95)),
      minHfov: 35,
      maxHfov: 140,
    });
  }

  loadPannellum()
    .then(() => renderViewer(state.image_url, state.image_data_url, state.hfov))
    .catch(() => renderMessage("Could not load 360 viewer assets."));

  return function cleanup() {
    if (container.__image360Widget && container.__image360Widget.cleanup) {
      container.__image360Widget.cleanup();
    }
  };
}
