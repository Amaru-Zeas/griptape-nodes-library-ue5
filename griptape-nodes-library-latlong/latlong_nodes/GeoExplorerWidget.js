/**
 * GeoExplorerWidget - quick Earth/Map/Street viewer with search box.
 */
export default function GeoExplorerWidget(container, props) {
  const { value, onChange, disabled, height } = props;
  let cesiumLoadPromise = null;

  function computeFrameHeight() {
    const hostWidth = Math.max(380, (container && container.clientWidth) ? container.clientWidth : 860);
    const sixteenByNine = Math.round((hostWidth - 14) * 9 / 16);
    const maxByNode = height && height > 0 ? Math.max(220, height - 120) : 520;
    return Math.max(220, Math.min(sixteenByNine, maxByNode));
  }

  function loadCesiumAssets() {
    if (window.Cesium) return Promise.resolve(window.Cesium);
    if (cesiumLoadPromise) return cesiumLoadPromise;

    cesiumLoadPromise = new Promise((resolve, reject) => {
      const cssId = "geo-cesium-css";
      if (!document.getElementById(cssId)) {
        const link = document.createElement("link");
        link.id = cssId;
        link.rel = "stylesheet";
        link.href = "https://cdn.jsdelivr.net/npm/cesium@1.120.0/Build/Cesium/Widgets/widgets.css";
        document.head.appendChild(link);
      }

      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/cesium@1.120.0/Build/Cesium/Cesium.js";
      script.async = true;
      script.onload = () => resolve(window.Cesium);
      script.onerror = () => reject(new Error("Failed to load Cesium assets"));
      document.body.appendChild(script);
    });

    return cesiumLoadPromise;
  }

  function readValue(raw) {
    if (!raw) return { url: "", mode: "earth", query: "" };
    if (typeof raw === "string") return { url: raw, mode: "earth", query: "" };
    return {
      url: (raw.url || "").trim(),
      mode: (raw.mode || "earth").toLowerCase(),
      query: (raw.query || "").trim(),
      capture_nonce: (raw.capture_nonce || "").trim(),
      latitude: Number(raw.latitude),
      longitude: Number(raw.longitude),
      zoom: raw.zoom,
      heading: raw.heading,
      pitch: raw.pitch,
      earth_url: raw.earth_url,
      earth_3d_url: raw.earth_3d_url,
      map_url: raw.map_url,
      street_view_url: raw.street_view_url,
      globe_style: (raw.globe_style || "satellite").toLowerCase(),
      node_version: (raw.node_version || "").trim(),
    };
  }

  function extractGoogleApiKey(data) {
    const candidates = [data && data.earth_url, data && data.map_url, data && data.street_view_url];
    for (let i = 0; i < candidates.length; i += 1) {
      const url = String(candidates[i] || "");
      const match = url.match(/[?&]key=([^&]+)/i);
      if (match && match[1]) return decodeURIComponent(match[1]);
    }
    return "";
  }

  function isLatLng(text) {
    if (!text) return false;
    return /^\s*[+-]?\d{1,2}(?:\.\d+)?\s*,\s*[+-]?\d{1,3}(?:\.\d+)?\s*$/.test(text);
  }

  function normalizeMode(mode) {
    const clean = (mode || "earth").toLowerCase();
    if (clean === "earth" || clean === "map" || clean === "street_view") return clean;
    return "earth";
  }

  function parseLatLng(text) {
    const raw = (text || "").trim();
    const match = raw.match(/^\s*([+-]?\d{1,2}(?:\.\d+)?)\s*,\s*([+-]?\d{1,3}(?:\.\d+)?)\s*$/);
    if (!match) return null;
    const lat = parseFloat(match[1]);
    const lng = parseFloat(match[2]);
    if (Number.isNaN(lat) || Number.isNaN(lng)) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return { lat, lng };
  }

  function wrapHeading(value) {
    const v = Number(value);
    if (!Number.isFinite(v)) return 0;
    return ((v % 360) + 360) % 360;
  }

  function clampPitch(value) {
    const v = Number(value);
    if (!Number.isFinite(v)) return 0;
    return Math.max(-89, Math.min(89, v));
  }

  function applyStreetCamera(url, heading, pitch) {
    try {
      const parsed = new URL(url, "https://maps.google.com");
      parsed.searchParams.set("heading", String(wrapHeading(heading)));
      parsed.searchParams.set("pitch", String(clampPitch(pitch)));
      return parsed.toString();
    } catch (err) {
      return url;
    }
  }

  function isIframeSafeStreetUrl(url) {
    const u = String(url || "");
    if (!u) return false;
    return (
      u.indexOf("/maps/embed/") !== -1 ||
      u.indexOf("output=svembed") !== -1 ||
      u.indexOf("output=embed") !== -1
    );
  }

  function buildClientUrls(query, mode, fallbackLat, fallbackLng) {
    const cleanQuery = (query || "").trim();
    const hasQuery = cleanQuery.length > 0;
    const queryValue = hasQuery ? cleanQuery : `${fallbackLat},${fallbackLng}`;
    const encoded = encodeURIComponent(queryValue);

    const urls = {
      map: `https://maps.google.com/maps?q=${encoded}&z=15&output=embed`,
      // Earth web is frequently blocked in iframes; use satellite map as Earth-like fallback.
      earth: `https://maps.google.com/maps?q=${encoded}&t=k&z=15&output=embed`,
      street_view: `https://maps.google.com/maps?q=${encoded}&z=18&output=embed`,
      earth_3d: `https://earth.google.com/web/search/${encoded}`,
    };

    if (isLatLng(queryValue)) {
      const parts = queryValue.split(",");
      const lat = parseFloat(parts[0]);
      const lng = parseFloat(parts[1]);
      if (!Number.isNaN(lat) && !Number.isNaN(lng)) {
        urls.earth = `https://maps.google.com/maps?q=${encodeURIComponent(`${lat.toFixed(6)},${lng.toFixed(6)}`)}&t=k&z=15&output=embed`;
        urls.street_view =
          "https://maps.google.com/maps?layer=c&cbll=" +
          `${lat.toFixed(6)},${lng.toFixed(6)}&cbp=11,0,0,0,0&output=svembed`;
        urls.earth_3d = `https://earth.google.com/web/@${lat.toFixed(6)},${lng.toFixed(6)},1200a,1400d,35y,0h,0t,0r`;
      }
    }

    if (mode === "earth_3d") return urls.earth_3d;
    return urls[normalizeMode(mode)] || urls.earth;
  }

  const initial = readValue(value);
  const frameHeight = computeFrameHeight();

  if (container.__geoExplorer && container.__geoExplorer.root) {
    const state = container.__geoExplorer;
    state.onChange = onChange;
    state.latest = initial;
    state.streetHeading = wrapHeading(initial.heading != null ? initial.heading : state.streetHeading);
    state.streetPitch = clampPitch(initial.pitch != null ? initial.pitch : state.streetPitch);
    if (state.nodeVersionEl) {
      state.nodeVersionEl.textContent = initial.node_version ? `Node ${initial.node_version}` : "";
    }
    state.input.value = initial.query || state.query || "";
    state.mode.value = normalizeMode(initial.mode || state.mode.value || "earth");
    state.globeStyle.value = initial.globe_style || state.globeStyle.value || "satellite";
    state.input.disabled = !!disabled;
    state.mode.disabled = !!disabled;
    state.globeStyle.disabled = !!disabled;
    state.goBtn.disabled = !!disabled;
    state.refreshBtn.disabled = !!disabled;
    state.streetHereBtn.disabled = !!disabled;
    state.captureBtn.disabled = !!disabled;
    state.frameArea.style.height = computeFrameHeight() + "px";
    state.globeStyle.style.display = state.mode.value === "earth" ? "" : "none";

    const incomingNonce = (initial.capture_nonce || "").trim();
    const isCaptureCycle = !!incomingNonce && incomingNonce !== (state.lastCaptureNonce || "");
    const sameMode = normalizeMode(initial.mode) === normalizeMode(state.mode && state.mode.value);
    if (initial.url && initial.url !== state.currentUrl) {
      // During capture-run cycles, preserve the currently displayed camera/view URL
      // instead of reloading to canonical backend URL.
      if (!(isCaptureCycle && sameMode)) {
        state.loadUrl(initial.url, false, true);
      }
    }
    state.lastCaptureNonce = incomingNonce;

    return state.cleanup;
  }

  container.innerHTML =
    '<div class="geo-explorer nodrag nowheel" style="' +
      "display:flex;flex-direction:column;gap:6px;padding:6px;background:#101010;border-radius:6px;" +
      'user-select:none;width:100%;box-sizing:border-box;">' +
      `<div class="frame-area" style="width:100%;height:${frameHeight}px;border-radius:6px;overflow:hidden;background:#000;">` +
        (initial.url
          ? `<iframe class="geo-frame" src="${initial.url}" style="width:100%;height:100%;border:none;" allow="autoplay; fullscreen; xr-spatial-tracking" allowfullscreen></iframe>`
          : '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#777;font-size:12px;text-align:center;padding:12px;">Run the node or type a place/lat,lng and click Go</div>') +
      "</div>" +
      '<div style="display:flex;gap:4px;align-items:center;">' +
        `<input class="geo-query" type="text" value="${initial.query || ""}" placeholder="City, street, or 40.6892,-74.0445" ` +
          'style="flex:1;padding:6px 8px;font-size:12px;background:#1d1d1d;border:1px solid #333;border-radius:4px;color:#ddd;outline:none;font-family:monospace;" ' +
          (disabled ? "disabled" : "") + " />" +
        '<select class="geo-mode" style="padding:6px 8px;font-size:12px;background:#1d1d1d;border:1px solid #333;border-radius:4px;color:#ddd;" ' +
          (disabled ? "disabled" : "") + ">" +
          '<option value="earth">Earth</option>' +
          '<option value="map">Map</option>' +
          '<option value="street_view">Street</option>' +
        "</select>" +
        '<select class="geo-globe-style" style="padding:6px 8px;font-size:12px;background:#1d1d1d;border:1px solid #333;border-radius:4px;color:#ddd;" ' +
          (disabled ? "disabled" : "") + ">" +
          '<option value="satellite">Satellite</option>' +
          '<option value="streets">Streets</option>' +
          '<option value="terrain">Terrain</option>' +
        "</select>" +
        '<button class="btn-go" style="padding:6px 10px;font-size:12px;background:#1a4b8a;border:1px solid #2a6bba;border-radius:4px;color:#fff;cursor:pointer;font-weight:bold;" ' +
          (disabled ? "disabled" : "") + ">Go</button>" +
        '<button class="btn-street-here" style="padding:6px 10px;font-size:12px;background:#5a3c91;border:1px solid #7d5cc3;border-radius:4px;color:#fff;cursor:pointer;" ' +
          (disabled ? "disabled" : "") + ">Street Here</button>" +
        '<button class="btn-capture" style="padding:6px 10px;font-size:12px;background:#2f6f5f;border:1px solid #4e9c86;border-radius:4px;color:#fff;cursor:pointer;" ' +
          (disabled ? "disabled" : "") + ">Capture</button>" +
        '<button class="btn-left" title="Turn left" style="padding:6px 8px;font-size:12px;background:#2a2a4a;border:1px solid #444;border-radius:4px;color:#ccc;cursor:pointer;" ' +
          (disabled ? "disabled" : "") + ">◀</button>" +
        '<button class="btn-right" title="Turn right" style="padding:6px 8px;font-size:12px;background:#2a2a4a;border:1px solid #444;border-radius:4px;color:#ccc;cursor:pointer;" ' +
          (disabled ? "disabled" : "") + ">▶</button>" +
        '<button class="btn-up" title="Look up" style="padding:6px 8px;font-size:12px;background:#2a2a4a;border:1px solid #444;border-radius:4px;color:#ccc;cursor:pointer;" ' +
          (disabled ? "disabled" : "") + ">▲</button>" +
        '<button class="btn-down" title="Look down" style="padding:6px 8px;font-size:12px;background:#2a2a4a;border:1px solid #444;border-radius:4px;color:#ccc;cursor:pointer;" ' +
          (disabled ? "disabled" : "") + ">▼</button>" +
        '<button class="btn-refresh" style="padding:6px 10px;font-size:12px;background:#2a2a4a;border:1px solid #444;border-radius:4px;color:#ccc;cursor:pointer;" ' +
          (disabled ? "disabled" : "") + ">↻</button>" +
      "</div>" +
      '<div style="font-size:11px;color:#8a8a8a;">Capture target: 16:9. Earth = in-node 3D globe. <span class="mesh-status">Mesh: initializing...</span> <span class="node-version" style="margin-left:8px;color:#6fb1ff;"></span></div>' +
    "</div>";

  const root = container.querySelector(".geo-explorer");
  const frameArea = container.querySelector(".frame-area");
  const input = container.querySelector(".geo-query");
  const mode = container.querySelector(".geo-mode");
  const globeStyle = container.querySelector(".geo-globe-style");
  const goBtn = container.querySelector(".btn-go");
  const streetHereBtn = container.querySelector(".btn-street-here");
  const captureBtn = container.querySelector(".btn-capture");
  const leftBtn = container.querySelector(".btn-left");
  const rightBtn = container.querySelector(".btn-right");
  const upBtn = container.querySelector(".btn-up");
  const downBtn = container.querySelector(".btn-down");
  const refreshBtn = container.querySelector(".btn-refresh");
  const meshStatusEl = container.querySelector(".mesh-status");
  const nodeVersionEl = container.querySelector(".node-version");
  let currentUrl = "";
  let query = initial.query || "";
  let currentOnChange = onChange;
  let streetHeading = wrapHeading(initial.heading || 0);
  let streetPitch = clampPitch(initial.pitch || 0);
  let cesiumViewer = null;
  let cesiumRenderErrorHandler = null;
  let meshPrimitive = null;
  let currentGoogleKey = extractGoogleApiKey(initial);

  mode.value = normalizeMode(initial.mode || "earth");
  globeStyle.value = initial.globe_style || "satellite";
  globeStyle.style.display = mode.value === "earth" ? "" : "none";
  if (nodeVersionEl) nodeVersionEl.textContent = initial.node_version ? `Node ${initial.node_version}` : "";

  function latestValue() {
    if (container.__geoExplorer && container.__geoExplorer.latest) return container.__geoExplorer.latest;
    return initial;
  }

  function clearMeshPrimitive() {
    if (!cesiumViewer || !meshPrimitive) return;
    try {
      cesiumViewer.scene.primitives.remove(meshPrimitive);
    } catch (err) {
      // no-op
    }
    meshPrimitive = null;
  }

  function setMeshStatus(text, color) {
    if (!meshStatusEl) return;
    meshStatusEl.textContent = text;
    meshStatusEl.style.color = color || "#8a8a8a";
  }

  function buildImageryProvider(Cesium, style) {
    if (style === "streets") {
      return new Cesium.UrlTemplateImageryProvider({
        url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        credit: "OpenStreetMap contributors",
      });
    }
    if (style === "terrain") {
      return new Cesium.UrlTemplateImageryProvider({
        url: "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        credit: "OpenTopoMap contributors",
      });
    }
    return new Cesium.UrlTemplateImageryProvider({
      // Often more reliable in embedded WebGL than ArcGIS tiles.
      url: "https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
      subdomains: ["0", "1", "2", "3"],
      credit: "Google",
    });
  }

  function applyImageryProvider(style) {
    if (!cesiumViewer || !window.Cesium) return;
    const Cesium = window.Cesium;
    const requestedStyle = style || "satellite";
    try {
      const provider = buildImageryProvider(Cesium, requestedStyle);
      let errorCount = 0;
      if (provider && provider.errorEvent) {
        provider.errorEvent.addEventListener(function() {
          errorCount += 1;
          if (errorCount >= 2 && requestedStyle !== "streets") {
            // If satellite/terrain tiles fail, hard-fallback to streets immediately.
            globeStyle.value = "streets";
            applyImageryProvider("streets");
          }
        });
      }
      cesiumViewer.imageryLayers.removeAll(true);
      cesiumViewer.imageryLayers.addImageryProvider(provider);
    } catch (err) {
      if (requestedStyle !== "streets") {
        globeStyle.value = "streets";
        applyImageryProvider("streets");
      }
    }
  }

  async function applyMeshLayer(Cesium) {
    if (!cesiumViewer || !Cesium) return;
    clearMeshPrimitive();
    cesiumViewer.scene.globe.show = true;
    setMeshStatus("Mesh: loading...", "#8a8a8a");

    // Best match to native Earth look (requires Maps Tiles-capable key).
    if (currentGoogleKey && typeof Cesium.createGooglePhotorealistic3DTileset === "function") {
      try {
        const tileset = await Cesium.createGooglePhotorealistic3DTileset({ apiKey: currentGoogleKey });
        meshPrimitive = cesiumViewer.scene.primitives.add(tileset);
        cesiumViewer.scene.globe.show = false;
        setMeshStatus("Mesh: Google photorealistic", "#72d572");
        return;
      } catch (err) {
        // Fallback to OSM buildings if Google photorealistic tiles are unavailable.
      }
    }

    // Lightweight fallback mesh so buildings still extrude above imagery.
    try {
      if (typeof Cesium.createOsmBuildingsAsync === "function") {
        const osmTileset = await Cesium.createOsmBuildingsAsync();
        meshPrimitive = cesiumViewer.scene.primitives.add(osmTileset);
        setMeshStatus("Mesh: OSM buildings", "#9cc6ff");
      } else if (typeof Cesium.createOsmBuildings === "function") {
        const osmTileset = Cesium.createOsmBuildings();
        meshPrimitive = cesiumViewer.scene.primitives.add(osmTileset);
        setMeshStatus("Mesh: OSM buildings", "#9cc6ff");
      }
    } catch (err) {
      setMeshStatus("Mesh: unavailable in this renderer", "#d4a373");
    }
  }

  function loadUrl(nextUrl, emitChange = true, force = false) {
    if (!nextUrl) return;
    if (!force && nextUrl === currentUrl) return;
    currentUrl = nextUrl;
    if (cesiumViewer) {
      clearMeshPrimitive();
      if (cesiumRenderErrorHandler && cesiumViewer.scene && cesiumViewer.scene.renderError) {
        try { cesiumViewer.scene.renderError.removeEventListener(cesiumRenderErrorHandler); } catch (err) { /* no-op */ }
      }
      cesiumRenderErrorHandler = null;
      try { cesiumViewer.destroy(); } catch (err) { /* no-op */ }
      cesiumViewer = null;
    }
    frameArea.innerHTML =
      `<iframe class="geo-frame" src="${nextUrl}" style="width:100%;height:100%;border:none;" allow="autoplay; fullscreen; xr-spatial-tracking" allowfullscreen></iframe>`;
    if (emitChange && currentOnChange) {
      currentOnChange({ url: nextUrl, mode: mode.value, query, heading: streetHeading, pitch: streetPitch });
    }
    setMeshStatus("Mesh: n/a for current mode", "#8a8a8a");
  }

  function resolveCenterFromState() {
    const latest = latestValue();
    const fromQuery = parseLatLng(query);
    if (fromQuery) return fromQuery;
    if (!Number.isNaN(latest.latitude) && !Number.isNaN(latest.longitude)) {
      return { lat: latest.latitude, lng: latest.longitude };
    }
    return { lat: 40.758, lng: -73.9855 };
  }

  function renderInNode3d() {
    const center = resolveCenterFromState();
    frameArea.innerHTML = '<div class="geo-cesium" style="width:100%;height:100%;"></div>';
    const target = frameArea.querySelector(".geo-cesium");
    if (!target) return;

    loadCesiumAssets()
      .then((Cesium) => {
        if (!Cesium) return;
        if (cesiumViewer) {
          if (cesiumRenderErrorHandler && cesiumViewer.scene && cesiumViewer.scene.renderError) {
            try { cesiumViewer.scene.renderError.removeEventListener(cesiumRenderErrorHandler); } catch (err) { /* no-op */ }
          }
          cesiumRenderErrorHandler = null;
          try { cesiumViewer.destroy(); } catch (err) { /* no-op */ }
        }

        cesiumViewer = new Cesium.Viewer(target, {
          animation: false,
          timeline: false,
          sceneModePicker: false,
          geocoder: false,
          baseLayerPicker: false,
          homeButton: true,
          navigationHelpButton: false,
          fullscreenButton: false,
          infoBox: false,
          selectionIndicator: false,
          terrainProvider: new Cesium.EllipsoidTerrainProvider(),
          imageryProvider: buildImageryProvider(Cesium, "streets"),
          scene3DOnly: true,
          shadows: false,
          orderIndependentTranslucency: false,
          requestRenderMode: true,
        });

        cesiumViewer.scene.globe.depthTestAgainstTerrain = false;
        cesiumViewer.scene.globe.showGroundAtmosphere = false;
        cesiumViewer.scene.skyAtmosphere.show = false;
        cesiumViewer.scene.fog.enabled = false;
        if (cesiumViewer.scene.postProcessStages && cesiumViewer.scene.postProcessStages.fxaa) {
          cesiumViewer.scene.postProcessStages.fxaa.enabled = false;
        }
        applyImageryProvider(globeStyle.value || "satellite");
        applyMeshLayer(Cesium);

        cesiumRenderErrorHandler = function() {
          // On weak/incompatible GPUs, shader compile can fail in embedded WebGL.
          // Fall back to stable map embed instead of leaving a broken canvas.
          const fallback = buildClientUrls(query, "map", initial.latitude || 0, initial.longitude || 0);
          loadUrl(fallback, true, true);
        };
        cesiumViewer.scene.renderError.addEventListener(cesiumRenderErrorHandler);

        cesiumViewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(center.lng, center.lat, 4000),
          orientation: {
            heading: 0.0,
            pitch: Cesium.Math.toRadians(-50),
            roll: 0.0,
          },
          duration: 1.6,
        });
      })
      .catch(() => {
        // Fallback to standard embed if Cesium fails for any reason.
        const fallback = buildClientUrls(query, "earth", initial.latitude || 0, initial.longitude || 0);
        loadUrl(fallback, true, true);
      });
  }

  function updateGlobeStyle() {
    if (!cesiumViewer || !window.Cesium) return;
    applyImageryProvider(globeStyle.value || "satellite");
    applyMeshLayer(window.Cesium);
  }

  function handleGlobeStyleChange(e) {
    stopProp(e);
    updateGlobeStyle();
    if (currentOnChange) currentOnChange({ url: currentUrl, mode: mode.value, query, globe_style: globeStyle.value });
  }

  function runGo(e) {
    if (disabled) return;
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }

    query = (input.value || "").trim();
    const latest = latestValue();
    currentGoogleKey = extractGoogleApiKey(latest);
    const nextMode = normalizeMode(mode.value);
    globeStyle.style.display = nextMode === "earth" ? "" : "none";
    let directUrl = "";
    const queryUnchanged = query === (latest.query || "");
    if (queryUnchanged) {
      if (nextMode === "earth" && latest.earth_url) directUrl = latest.earth_url;
      if (nextMode === "map" && latest.map_url) directUrl = latest.map_url;
      if (nextMode === "street_view" && latest.street_view_url && isIframeSafeStreetUrl(latest.street_view_url)) {
        directUrl = latest.street_view_url;
      } else if (nextMode === "street_view" && isIframeSafeStreetUrl(currentUrl)) {
        // Preserve currently working iframe URL when backend URL is non-embeddable.
        directUrl = currentUrl;
      }
    }
    if (!directUrl) {
      directUrl = buildClientUrls(query, nextMode, latest.latitude || 0, latest.longitude || 0);
    }
    if (nextMode === "street_view") {
      directUrl = applyStreetCamera(directUrl, streetHeading, streetPitch);
    }
    if (container.__geoExplorer) {
      container.__geoExplorer.streetHeading = streetHeading;
      container.__geoExplorer.streetPitch = streetPitch;
    }
    if (nextMode === "earth") {
      renderInNode3d();
      if (currentOnChange) currentOnChange({ url: directUrl, mode: nextMode, query, globe_style: globeStyle.value, heading: streetHeading, pitch: streetPitch });
      return;
    }
    loadUrl(directUrl, true, true);
  }

  function runRefresh(e) {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    const frame = frameArea.querySelector(".geo-frame");
    if (frame) frame.src = frame.src;
  }

  function runStreetHere(e) {
    if (disabled) return;
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    mode.value = "street_view";
    runGo(e);
  }

  function runCapture(e) {
    if (disabled) return;
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    const nonce = String(Date.now());
    query = (input.value || "").trim();
    const frame = frameArea.querySelector(".geo-frame");
    const liveUrl = (frame && frame.src) ? String(frame.src) : currentUrl;
    if (liveUrl) currentUrl = liveUrl;
    if (currentOnChange) {
      currentOnChange({
        url: liveUrl || currentUrl,
        mode: mode.value,
        query,
        globe_style: globeStyle.value,
        heading: streetHeading,
        pitch: streetPitch,
        capture_nonce: nonce,
      });
    }
  }

  function nudgeStreetCamera(deltaHeading, deltaPitch, e) {
    if (disabled) return;
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    streetHeading = wrapHeading(streetHeading + deltaHeading);
    streetPitch = clampPitch(streetPitch + deltaPitch);
    if (container.__geoExplorer) {
      container.__geoExplorer.streetHeading = streetHeading;
      container.__geoExplorer.streetPitch = streetPitch;
    }
    if (mode.value === "street_view") runGo(e);
  }

  function onLeftClick(e) { nudgeStreetCamera(-25, 0, e); }
  function onRightClick(e) { nudgeStreetCamera(25, 0, e); }
  function onUpClick(e) { nudgeStreetCamera(0, 10, e); }
  function onDownClick(e) { nudgeStreetCamera(0, -10, e); }

  function onKeyDown(e) {
    e.stopPropagation();
    if (e.key === "Enter") runGo(e);
  }

  function stopProp(e) {
    e.stopPropagation();
  }

  goBtn.addEventListener("click", runGo);
  streetHereBtn.addEventListener("click", runStreetHere);
  captureBtn.addEventListener("click", runCapture);
  leftBtn.addEventListener("click", onLeftClick);
  rightBtn.addEventListener("click", onRightClick);
  upBtn.addEventListener("click", onUpClick);
  downBtn.addEventListener("click", onDownClick);
  refreshBtn.addEventListener("click", runRefresh);
  input.addEventListener("keydown", onKeyDown);
  input.addEventListener("keyup", stopProp);
  input.addEventListener("input", stopProp);
  mode.addEventListener("change", runGo);
  globeStyle.addEventListener("change", handleGlobeStyleChange);
  root.addEventListener("pointerdown", stopProp);
  root.addEventListener("mousedown", stopProp);

  if (initial.url) {
    if (mode.value === "earth") renderInNode3d();
    else loadUrl(initial.url, false, true);
  }

  function cleanup() {
    goBtn.removeEventListener("click", runGo);
    streetHereBtn.removeEventListener("click", runStreetHere);
    captureBtn.removeEventListener("click", runCapture);
    leftBtn.removeEventListener("click", onLeftClick);
    rightBtn.removeEventListener("click", onRightClick);
    upBtn.removeEventListener("click", onUpClick);
    downBtn.removeEventListener("click", onDownClick);
    refreshBtn.removeEventListener("click", runRefresh);
    input.removeEventListener("keydown", onKeyDown);
    input.removeEventListener("keyup", stopProp);
    input.removeEventListener("input", stopProp);
    mode.removeEventListener("change", runGo);
    globeStyle.removeEventListener("change", handleGlobeStyleChange);
    root.removeEventListener("pointerdown", stopProp);
    root.removeEventListener("mousedown", stopProp);
    if (cesiumViewer) {
      clearMeshPrimitive();
      if (cesiumRenderErrorHandler && cesiumViewer.scene && cesiumViewer.scene.renderError) {
        try { cesiumViewer.scene.renderError.removeEventListener(cesiumRenderErrorHandler); } catch (err) { /* no-op */ }
      }
      cesiumRenderErrorHandler = null;
      try { cesiumViewer.destroy(); } catch (err) { /* no-op */ }
      cesiumViewer = null;
    }
    if (container.__geoExplorer) container.__geoExplorer = null;
  }

  container.__geoExplorer = {
    root,
    frameArea,
    input,
    mode,
    globeStyle,
    goBtn,
    streetHereBtn,
    captureBtn,
    refreshBtn,
    leftBtn,
    rightBtn,
    upBtn,
    downBtn,
    nodeVersionEl,
    streetHeading,
    streetPitch,
    lastCaptureNonce: (initial.capture_nonce || "").trim(),
    latest: initial,
    currentUrl,
    query,
    onChange: currentOnChange,
    loadUrl: function(nextUrl, emitChange, force) {
      currentOnChange = container.__geoExplorer ? container.__geoExplorer.onChange : currentOnChange;
      loadUrl(nextUrl, emitChange, force);
      if (container.__geoExplorer) {
        container.__geoExplorer.currentUrl = currentUrl;
        container.__geoExplorer.query = query;
      }
    },
    cleanup,
  };

  return cleanup;
}
