/**
 * BlenderViewport - iframe web viewer with session-preserving rerenders.
 */
export default function BlenderViewport(container, props) {
  const { value, onChange, disabled, height } = props;

  let url = '';
  if (typeof value === 'string') url = value;
  else if (value && typeof value === 'object') url = value.url || '';
  url = (url || '').trim();

  const frameHeight = height && height > 0 ? Math.max(220, height - 60) : 420;

  // If already initialized in this container, update in place to avoid
  // tearing down the iframe session on every node state refresh.
  if (container.__blenderVp && container.__blenderVp.root) {
    const state = container.__blenderVp;
    state.onChange = onChange;
    state.input.value = url || state.currentUrl || '';
    state.input.disabled = !!disabled;
    state.loadBtn.disabled = !!disabled;
    state.refreshBtn.disabled = !!disabled;
    state.frameArea.style.height = frameHeight + 'px';

    if (url && url !== state.currentUrl) {
      state.loadUrl(url, false, true);
    }

    return state.cleanup;
  }

  container.innerHTML =
    '<div class="blender-vp nodrag nowheel" style="' +
      'display:flex;flex-direction:column;gap:6px;padding:6px;' +
      'background:#111;border-radius:6px;user-select:none;width:100%;box-sizing:border-box;">' +
      '<div class="frame-area" style="width:100%;height:' + frameHeight +
        'px;border-radius:6px;overflow:hidden;background:#000;">' +
        (url
          ? '<iframe class="vp-frame" src="' + url + '" style="width:100%;height:100%;border:none;" ' +
            'allow="autoplay; fullscreen; xr-spatial-tracking; clipboard-write" allowfullscreen></iframe>'
          : '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#666;font-size:12px;">' +
            'Paste a Blender stream URL below and click Load</div>'
        ) +
      '</div>' +
      '<div style="display:flex;gap:4px;align-items:center;">' +
        '<input class="url-input" type="text" value="' + url + '" ' +
          'placeholder="https://your-stream-url" style="flex:1;padding:6px 8px;font-size:12px;' +
          'background:#1b1b1b;border:1px solid #333;border-radius:4px;color:#ddd;outline:none;font-family:monospace;" ' +
          (disabled ? 'disabled' : '') + ' />' +
        '<button class="btn-load" style="padding:6px 10px;font-size:12px;background:#1a4b8a;' +
          'border:1px solid #2a6bba;border-radius:4px;color:#fff;cursor:pointer;font-weight:bold;" ' +
          (disabled ? 'disabled' : '') + '>Load</button>' +
        '<button class="btn-refresh" style="padding:6px 10px;font-size:12px;background:#2a2a4a;' +
          'border:1px solid #444;border-radius:4px;color:#ccc;cursor:pointer;" ' +
          (disabled ? 'disabled' : '') + '>↻</button>' +
      '</div>' +
    '</div>';

  const root = container.querySelector('.blender-vp');
  const frameArea = container.querySelector('.frame-area');
  const input = container.querySelector('.url-input');
  const loadBtn = container.querySelector('.btn-load');
  const refreshBtn = container.querySelector('.btn-refresh');
  let currentUrl = '';
  let currentOnChange = onChange;

  function loadUrl(nextUrl, emitChange = true, force = false) {
    if (!nextUrl) return;
    if (nextUrl.indexOf('://') === -1) nextUrl = 'https://' + nextUrl;
    if (!force && nextUrl === currentUrl) return;
    currentUrl = nextUrl;

    frameArea.innerHTML =
      '<iframe class="vp-frame" src="' + nextUrl + '" style="width:100%;height:100%;border:none;" ' +
      'allow="autoplay; fullscreen; xr-spatial-tracking; clipboard-write" allowfullscreen></iframe>';

    if (emitChange && currentOnChange) currentOnChange({ url: nextUrl });
  }

  function handleLoad(e) {
    if (disabled) return;
    e.stopPropagation();
    e.preventDefault();
    const nextUrl = input.value.trim();
    if (nextUrl) loadUrl(nextUrl);
  }

  function handleRefresh(e) {
    e.stopPropagation();
    e.preventDefault();
    const frame = frameArea.querySelector('.vp-frame');
    if (frame) frame.src = frame.src;
  }

  function onKeyDown(e) {
    e.stopPropagation();
    if (e.key === 'Enter') handleLoad(e);
  }

  function stopProp(e) {
    e.stopPropagation();
  }

  if (url) loadUrl(url, false, true);

  loadBtn.addEventListener('click', handleLoad);
  refreshBtn.addEventListener('click', handleRefresh);
  input.addEventListener('keydown', onKeyDown);
  input.addEventListener('keyup', stopProp);
  input.addEventListener('input', stopProp);
  root.addEventListener('pointerdown', stopProp);
  root.addEventListener('mousedown', stopProp);

  function cleanup() {
    loadBtn.removeEventListener('click', handleLoad);
    refreshBtn.removeEventListener('click', handleRefresh);
    input.removeEventListener('keydown', onKeyDown);
    input.removeEventListener('keyup', stopProp);
    input.removeEventListener('input', stopProp);
    root.removeEventListener('pointerdown', stopProp);
    root.removeEventListener('mousedown', stopProp);
    if (container.__blenderVp) container.__blenderVp = null;
  }

  container.__blenderVp = {
    root,
    frameArea,
    input,
    loadBtn,
    refreshBtn,
    currentUrl,
    onChange: currentOnChange,
    loadUrl: function (nextUrl, emitChange, force) {
      currentOnChange = container.__blenderVp ? container.__blenderVp.onChange : currentOnChange;
      loadUrl(nextUrl, emitChange, force);
      if (container.__blenderVp) container.__blenderVp.currentUrl = currentUrl;
    },
    cleanup,
  };

  return cleanup;
}
