/**
 * VideoFrameEditorWidget
 * - Load local video
 * - Scrub by frame index (not seconds)
 * - Step frames with buttons or mouse wheel
 * - Extract current frame as PNG data URL
 */

const WIDGET_SESSION_BY_KEY = new Map();

export default function VideoFrameEditorWidget(container, props) {
  const { value, onChange, disabled, height } = props;
  const WIDGET_VERSION = 'v2.5.0-cache10';
  const DEFAULT_FPS = 24;
  const MIN_FPS = 1;
  const MAX_FPS = 240;
  const clampNumber = (n, min, max) => Math.max(min, Math.min(max, n));

  const sessionKey = String(props?.node_id || props?.nodeId || props?.id || 'gtn-video-frame-editor-default');
  const session = WIDGET_SESSION_BY_KEY.get(sessionKey) || {
    selectedFile: null,
    fps: null,
    frameIndex: 0,
    currentTime: 0,
    frameImageData: '',
    videoName: '',
  };
  WIDGET_SESSION_BY_KEY.set(sessionKey, session);

  const parsedSessionFps = Number(session.fps);
  const parsedValueFps = Number(value?.fps);
  const initialFps = Number.isFinite(parsedSessionFps)
    ? clampNumber(parsedSessionFps, MIN_FPS, MAX_FPS)
    : (Number.isFinite(parsedValueFps) ? clampNumber(parsedValueFps, MIN_FPS, MAX_FPS) : DEFAULT_FPS);
  const initialFrameImage = session.frameImageData || (typeof value?.frame_image_data === 'string' ? value.frame_image_data : '');

  const viewportHeight = height && height > 0 ? Math.max(220, height - 390) : 320;

  container.innerHTML = `
    <div class="vfe-root nodrag" style="
      display:flex;flex-direction:column;gap:8px;padding:8px;
      background:#111;border-radius:8px;color:#ddd;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:12px;">

      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:space-between;">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        <label class="vfe-file-btn" style="
          background:#1f2b44;border:1px solid #34507f;border-radius:6px;
          padding:6px 10px;cursor:pointer;font-size:12px;">
          Import Video
          <input type="file" class="vfe-file-input" accept="video/*" style="display:none;" />
        </label>
        <span class="vfe-file-name" style="color:#8da4d1;">No video loaded</span>
        </div>
        <span class="vfe-version-badge" style="
          color:#89e0ff;background:#14202c;border:1px solid #2d5f7a;
          border-radius:999px;padding:2px 8px;font-size:11px;white-space:nowrap;">
          ${WIDGET_VERSION}
        </span>
      </div>

      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
        <label style="display:flex;align-items:center;gap:6px;">
          FPS
          <input class="vfe-fps-input" type="number" min="1" step="0.001" value="${initialFps}" style="
            width:86px;background:#1a1a1a;border:1px solid #444;color:#eee;border-radius:4px;padding:3px 6px;" />
        </label>
        <span class="vfe-meta" style="color:#9a9a9a;">Frame 0 of 0 | 0.000s</span>
      </div>

      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        <button class="vfe-btn vfe-prev">Prev Frame</button>
        <button class="vfe-btn vfe-next">Next Frame</button>
        <button class="vfe-btn vfe-play">Play</button>
        <button class="vfe-btn vfe-pause">Pause</button>
        <button class="vfe-btn vfe-extract" style="background:#2c4b2f;border-color:#3f7a45;">Extract Frame (PNG)</button>
        <img class="vfe-mini-preview" alt="Extracted frame preview" style="
          width:42px;height:28px;object-fit:cover;border-radius:4px;border:1px solid #2f5f37;
          display:${initialFrameImage ? 'block' : 'none'};" />
      </div>

      <input class="vfe-slider" type="range" min="0" max="0" step="1" value="0" style="width:100%;accent-color:#62a9ff;" />

      <div class="vfe-viewport-wrap nowheel" style="
        width:100%;height:${viewportHeight}px;background:#000;border-radius:6px;
        border:1px solid #2d2d2d;position:relative;overflow:hidden;">
        <video class="vfe-video" style="width:100%;height:100%;object-fit:contain;background:#000;" playsinline preload="metadata"></video>
        <div class="vfe-overlay" style="
          position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
          color:#707070;font-size:12px;pointer-events:none;">Load a video to begin</div>
      </div>

      <details style="background:#171717;border-radius:6px;padding:6px 8px;">
        <summary style="cursor:pointer;color:#a7a7a7;">Last Extracted Frame Preview</summary>
        <div style="margin-top:8px;">
          <img class="vfe-preview" style="max-width:100%;max-height:220px;border:1px solid #333;border-radius:4px;display:${initialFrameImage ? 'block' : 'none'};" />
          <div class="vfe-preview-empty" style="color:#666;display:${initialFrameImage ? 'none' : 'block'};">No frame extracted yet.</div>
        </div>
      </details>
    </div>
  `;

  const style = document.createElement('style');
  style.textContent = `
    .vfe-btn{
      background:#252525;border:1px solid #444;border-radius:6px;color:#ddd;
      padding:6px 10px;font-size:12px;cursor:pointer;
    }
    .vfe-btn:hover{background:#343434;border-color:#666;}
    .vfe-btn:active{background:#454545;}
    .vfe-btn:disabled,.vfe-file-btn.disabled{opacity:0.45;cursor:not-allowed;}
  `;
  container.appendChild(style);

  const root = container.querySelector('.vfe-root');
  const fileInput = container.querySelector('.vfe-file-input');
  const fileButton = container.querySelector('.vfe-file-btn');
  const fileNameEl = container.querySelector('.vfe-file-name');
  const fpsInput = container.querySelector('.vfe-fps-input');
  const metaEl = container.querySelector('.vfe-meta');
  const prevBtn = container.querySelector('.vfe-prev');
  const nextBtn = container.querySelector('.vfe-next');
  const playBtn = container.querySelector('.vfe-play');
  const pauseBtn = container.querySelector('.vfe-pause');
  const extractBtn = container.querySelector('.vfe-extract');
  const miniPreview = container.querySelector('.vfe-mini-preview');
  const slider = container.querySelector('.vfe-slider');
  const video = container.querySelector('.vfe-video');
  const overlay = container.querySelector('.vfe-overlay');
  const previewImg = container.querySelector('.vfe-preview');
  const previewEmpty = container.querySelector('.vfe-preview-empty');
  const viewportWrap = container.querySelector('.vfe-viewport-wrap');

  let objectUrl = null;
  let duration = 0;
  let fps = initialFps;
  let totalFrames = 0;
  let frameIndex = 0;
  let suppressSeekSync = false;
  let frameImageData = initialFrameImage;
  let loadedVideoName = session.videoName || (typeof value?.video_name === 'string' ? value.video_name : '');
  let loadFailTimeout = null;
  let canRenderFrame = false;

  if (frameImageData) {
    previewImg.src = frameImageData;
    miniPreview.src = frameImageData;
  }

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function computeTotalFrames() {
    if (!Number.isFinite(duration) || duration <= 0 || !Number.isFinite(fps) || fps <= 0) {
      return 0;
    }
    return Math.max(1, Math.round(duration * fps));
  }

  function hasSeekableTimeline() {
    return Number.isFinite(duration) && duration > 0 && Number.isFinite(fps) && fps > 0;
  }

  function saveSessionState() {
    session.fps = fps;
    session.frameIndex = frameIndex;
    session.currentTime = Number.isFinite(video.currentTime) ? video.currentTime : 0;
    session.frameImageData = frameImageData || '';
    session.videoName = loadedVideoName || '';
  }

  function updateUiState() {
    totalFrames = computeTotalFrames();

    const maxFrame = Math.max(0, totalFrames - 1);
    frameIndex = clamp(frameIndex, 0, maxFrame);
    slider.max = String(maxFrame);
    slider.value = String(frameIndex);
    fpsInput.value = String(clampNumber(fps, MIN_FPS, MAX_FPS));

    const currentTime = Number.isFinite(video.currentTime) ? video.currentTime : 0;
    metaEl.textContent = `Frame ${frameIndex} of ${maxFrame} | ${currentTime.toFixed(3)}s`;
    fileNameEl.textContent = loadedVideoName || 'No video loaded';

    const hasVideo = !!objectUrl && canRenderFrame;
    const canStep = hasVideo && hasSeekableTimeline() && totalFrames > 0;
    prevBtn.disabled = !canStep || disabled;
    nextBtn.disabled = !canStep || disabled;
    playBtn.disabled = !hasVideo || disabled;
    pauseBtn.disabled = !hasVideo || disabled;
    extractBtn.disabled = !hasVideo || disabled;
    slider.disabled = !canStep || disabled;
    fpsInput.disabled = disabled;
    fileInput.disabled = disabled;

    if (disabled) {
      fileButton.classList.add('disabled');
    } else {
      fileButton.classList.remove('disabled');
    }
    saveSessionState();
  }

  function emit(extra = {}) {
    if (!onChange || disabled) return;
    const payload = {
      fps,
      frame_index: frameIndex,
      frame_time_seconds: Number.isFinite(video.currentTime) ? video.currentTime : 0,
      total_frames: totalFrames,
      video_name: loadedVideoName,
      frame_image_data: frameImageData,
      ...extra,
    };
    onChange(payload);
  }

  function emitFrameOnly() {
    if (!onChange || disabled) return;
    onChange({
      frame_image_data: frameImageData,
      extract_nonce: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    });
  }

  function seekToFrame(targetFrame, shouldEmit = true) {
    if (!objectUrl || !hasSeekableTimeline()) return;
    const maxFrame = Math.max(0, totalFrames - 1);
    frameIndex = clamp(targetFrame, 0, maxFrame);
    const targetTime = frameIndex / fps;
    const maxTime = Math.max(0, duration - (1 / fps) * 0.1);
    const safeTime = clamp(targetTime, 0, maxTime);

    suppressSeekSync = !shouldEmit;
    video.currentTime = safeTime;
    updateUiState();
  }

  function stepFrame(delta) {
    seekToFrame(frameIndex + delta, true);
  }

  function extractFrame() {
    if (!objectUrl || !video.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    frameImageData = canvas.toDataURL('image/png');
    previewImg.src = frameImageData;
    previewImg.style.display = 'block';
    previewEmpty.style.display = 'none';
    miniPreview.src = frameImageData;
    miniPreview.style.display = 'block';
    // Extraction is an explicit sync point to avoid widget reset loops.
    emitFrameOnly();
  }

  function onVideoLoadedMetadata() {
    if (loadFailTimeout) {
      clearTimeout(loadFailTimeout);
      loadFailTimeout = null;
    }
    duration = Number.isFinite(video.duration) ? video.duration : 0;
    if (!duration || duration <= 0 || !Number.isFinite(duration)) {
      // Some generated videos report duration late/oddly; keep widget usable.
      overlay.textContent = 'Video loaded, waiting for timeline metadata...';
      overlay.style.display = 'flex';
      canRenderFrame = (video.videoWidth > 0 && video.videoHeight > 0) || video.readyState >= 2;
      updateUiState();
      return;
    }

    totalFrames = computeTotalFrames();
    frameIndex = hasSeekableTimeline()
      ? clamp(Math.round((session.currentTime || 0) * fps), 0, Math.max(0, totalFrames - 1))
      : 0;
    overlay.style.display = 'none';
    // Some codecs do not render frame 0 reliably; nudge if no previous time exists.
    if ((session.currentTime || 0) > 0) {
      seekToFrame(frameIndex, false);
    } else {
      seekToFrame(Math.min(1, Math.max(0, totalFrames - 1)), false);
    }
    updateUiState();
  }

  function onVideoLoadedData() {
    if (loadFailTimeout) {
      clearTimeout(loadFailTimeout);
      loadFailTimeout = null;
    }
    canRenderFrame = true;
    overlay.style.display = 'none';
    updateUiState();
  }

  function onVideoCanPlay() {
    canRenderFrame = true;
    if (overlay.textContent.includes('waiting for timeline')) {
      overlay.style.display = 'none';
    }
    updateUiState();
  }

  function onDurationChange() {
    const d = Number.isFinite(video.duration) ? video.duration : 0;
    if (d > 0) {
      duration = d;
      updateUiState();
    }
  }

  function onVideoError() {
    if (loadFailTimeout) {
      clearTimeout(loadFailTimeout);
      loadFailTimeout = null;
    }
    duration = 0;
    totalFrames = 0;
    frameIndex = 0;
    canRenderFrame = false;
    overlay.textContent = 'This video format/codec is not supported here. Try MP4 (H.264).';
    overlay.style.display = 'flex';
    updateUiState();
  }

  function onVideoSeeked() {
    if (!Number.isFinite(fps) || fps <= 0) return;
    const maxFrame = Math.max(0, totalFrames - 1);
    const computedFrame = clamp(Math.round(video.currentTime * fps), 0, maxFrame);
    frameIndex = computedFrame;
    updateUiState();
    // Do not emit continuously while scrubbing; GTN can re-render and drop video source.
    suppressSeekSync = false;
  }

  function onFpsChanged() {
    const parsed = Number(fpsInput.value);
    if (!Number.isFinite(parsed)) {
      fpsInput.value = String(fps);
      return;
    }

    const currentFrame = frameIndex;
    fps = clampNumber(parsed, MIN_FPS, MAX_FPS);
    totalFrames = computeTotalFrames();
    seekToFrame(currentFrame, true);
    updateUiState();
  }

  function onFileSelected(ev) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;

    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }

    loadedVideoName = file.name;
    session.selectedFile = file;
    session.currentTime = 0;
    session.frameIndex = 0;
    session.videoName = loadedVideoName;
    objectUrl = URL.createObjectURL(file);
    video.src = objectUrl;
    video.load();
    canRenderFrame = false;
    overlay.textContent = 'Loading video metadata...';
    overlay.style.display = 'flex';

    // Clear previous extracted image when a new video is loaded.
    frameImageData = '';
    previewImg.src = '';
    previewImg.style.display = 'none';
    previewEmpty.style.display = 'block';
    miniPreview.src = '';
    miniPreview.style.display = 'none';

    if (loadFailTimeout) clearTimeout(loadFailTimeout);
    loadFailTimeout = setTimeout(() => {
      if (!canRenderFrame) {
        overlay.textContent = 'Still loading... if this stays, convert to MP4 H.264.';
        overlay.style.display = 'flex';
      }
    }, 2500);

    updateUiState();
  }

  function stopProp(e) {
    e.stopPropagation();
  }

  function onWheelStep(e) {
    // Wheel up/down snaps one frame at a time for precise review.
    if (!objectUrl || duration <= 0 || disabled) return;
    e.preventDefault();
    e.stopPropagation();
    const delta = e.deltaY > 0 ? 1 : -1;
    stepFrame(delta);
  }

  function onPrevClick() {
    stepFrame(-1);
  }

  function onNextClick() {
    stepFrame(1);
  }

  function onPlayClick() {
    video.play().catch(() => {});
  }

  function onPauseClick() {
    video.pause();
  }

  function onSliderInput() {
    seekToFrame(Number(slider.value), true);
  }

  function restoreSelectedFileFromSession() {
    if (!(session.selectedFile instanceof File)) return;
    loadedVideoName = session.selectedFile.name;
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    objectUrl = URL.createObjectURL(session.selectedFile);
    video.src = objectUrl;
    video.load();
    overlay.textContent = 'Restoring video...';
    overlay.style.display = 'flex';
    canRenderFrame = false;
    updateUiState();
  }

  fileInput.addEventListener('change', onFileSelected);
  video.addEventListener('loadedmetadata', onVideoLoadedMetadata);
  video.addEventListener('loadeddata', onVideoLoadedData);
  video.addEventListener('canplay', onVideoCanPlay);
  video.addEventListener('durationchange', onDurationChange);
  video.addEventListener('seeked', onVideoSeeked);
  video.addEventListener('error', onVideoError);
  fpsInput.addEventListener('change', onFpsChanged);
  prevBtn.addEventListener('click', onPrevClick);
  nextBtn.addEventListener('click', onNextClick);
  playBtn.addEventListener('click', onPlayClick);
  pauseBtn.addEventListener('click', onPauseClick);
  extractBtn.addEventListener('click', extractFrame);
  slider.addEventListener('input', onSliderInput);
  root.addEventListener('pointerdown', stopProp);
  root.addEventListener('mousedown', stopProp);
  viewportWrap.addEventListener('wheel', onWheelStep, { passive: false });

  if (disabled) {
    root.style.opacity = '0.8';
  }

  if (!objectUrl) {
    restoreSelectedFileFromSession();
  }

  updateUiState();

  return () => {
    fileInput.removeEventListener('change', onFileSelected);
    video.removeEventListener('loadedmetadata', onVideoLoadedMetadata);
    video.removeEventListener('loadeddata', onVideoLoadedData);
    video.removeEventListener('canplay', onVideoCanPlay);
    video.removeEventListener('durationchange', onDurationChange);
    video.removeEventListener('seeked', onVideoSeeked);
    video.removeEventListener('error', onVideoError);
    fpsInput.removeEventListener('change', onFpsChanged);
    prevBtn.removeEventListener('click', onPrevClick);
    nextBtn.removeEventListener('click', onNextClick);
    playBtn.removeEventListener('click', onPlayClick);
    pauseBtn.removeEventListener('click', onPauseClick);
    extractBtn.removeEventListener('click', extractFrame);
    slider.removeEventListener('input', onSliderInput);
    root.removeEventListener('pointerdown', stopProp);
    root.removeEventListener('mousedown', stopProp);
    viewportWrap.removeEventListener('wheel', onWheelStep);
    if (loadFailTimeout) clearTimeout(loadFailTimeout);
    saveSessionState();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  };
}
