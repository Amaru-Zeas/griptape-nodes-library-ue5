/**
 * BlenderCameraViewport
 * - Dropdown camera picker
 * - Snapshot preview image (from bridge /viewport/snapshot)
 */
export default function BlenderCameraViewport(container, props) {
  const { value, onChange, disabled, height } = props;
  const v = (value && typeof value === 'object') ? value : {};

  const cameraList = Array.isArray(v.cameraList) ? v.cameraList : [];
  const selected = (v.selectedCamera || cameraList[0] || 'Camera');
  const imageDataUrl = v.imageDataUrl || '';
  const status = v.status || 'Ready';
  const host = v.host || '127.0.0.1';
  const port = Number.isFinite(v.port) ? v.port : 8765;
  const w = Number.isFinite(v.width) ? v.width : 1280;
  const h = Number.isFinite(v.height) ? v.height : 720;

  const previewHeight = height && height > 0 ? Math.max(220, height - 120) : 300;

  const options = cameraList.map(function (name) {
    const sel = name === selected ? ' selected' : '';
    return '<option value="' + name + '"' + sel + '>' + name + '</option>';
  }).join('');

  container.innerHTML =
    '<div class="bcv nodrag nowheel" style="display:flex;flex-direction:column;gap:6px;padding:6px;background:#121212;border-radius:6px;">' +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<label style="font-size:12px;color:#bbb;">Camera:</label>' +
        '<select class="cam-select" style="flex:1;background:#1f1f1f;color:#ddd;border:1px solid #333;padding:5px;border-radius:4px;" ' + (disabled ? 'disabled' : '') + '>' +
          (options || '<option value="' + selected + '">' + selected + '</option>') +
        '</select>' +
        '<button class="btn-apply" style="padding:6px 10px;font-size:12px;background:#1a4b8a;border:1px solid #2a6bba;border-radius:4px;color:#fff;cursor:pointer;" ' + (disabled ? 'disabled' : '') + '>Apply</button>' +
      '</div>' +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<label style="font-size:12px;color:#bbb;">Host</label>' +
        '<input class="host-input" type="text" value="' + host + '" style="width:120px;background:#1f1f1f;color:#ddd;border:1px solid #333;padding:5px;border-radius:4px;" ' + (disabled ? 'disabled' : '') + ' />' +
        '<label style="font-size:12px;color:#bbb;">Port</label>' +
        '<input class="port-input" type="number" value="' + port + '" style="width:90px;background:#1f1f1f;color:#ddd;border:1px solid #333;padding:5px;border-radius:4px;" ' + (disabled ? 'disabled' : '') + ' />' +
        '<label style="font-size:12px;color:#bbb;">W</label>' +
        '<input class="w-input" type="number" value="' + w + '" style="width:84px;background:#1f1f1f;color:#ddd;border:1px solid #333;padding:5px;border-radius:4px;" ' + (disabled ? 'disabled' : '') + ' />' +
        '<label style="font-size:12px;color:#bbb;">H</label>' +
        '<input class="h-input" type="number" value="' + h + '" style="width:84px;background:#1f1f1f;color:#ddd;border:1px solid #333;padding:5px;border-radius:4px;" ' + (disabled ? 'disabled' : '') + ' />' +
      '</div>' +
      '<div class="preview" style="width:100%;height:' + previewHeight + 'px;background:#000;border:1px solid #222;border-radius:6px;overflow:hidden;display:flex;align-items:center;justify-content:center;">' +
        (imageDataUrl
          ? '<img src="' + imageDataUrl + '" style="max-width:100%;max-height:100%;object-fit:contain;" />'
          : '<div style="color:#777;font-size:12px;">Run flow to capture camera viewport snapshot</div>') +
      '</div>' +
      '<div class="status" style="font-size:11px;color:#9ac;padding:2px 0;">' + status + '</div>' +
    '</div>';

  const root = container.querySelector('.bcv');
  const camSelect = container.querySelector('.cam-select');
  const hostInput = container.querySelector('.host-input');
  const portInput = container.querySelector('.port-input');
  const wInput = container.querySelector('.w-input');
  const hInput = container.querySelector('.h-input');
  const applyBtn = container.querySelector('.btn-apply');

  function emit(e) {
    if (e) {
      e.stopPropagation();
      if (e.type === 'click' || e.key === 'Enter') e.preventDefault();
    }
    if (!onChange) return;
    onChange({
      host: (hostInput.value || '127.0.0.1').trim(),
      port: parseInt(portInput.value || '8765', 10),
      selectedCamera: (camSelect.value || selected).trim(),
      width: parseInt(wInput.value || '1280', 10),
      height: parseInt(hInput.value || '720', 10),
      cameraList: cameraList,
      imageDataUrl: imageDataUrl,
      status: status,
    });
  }

  function onKey(e) {
    e.stopPropagation();
    if (e.key === 'Enter') emit(e);
  }
  function stopProp(e) { e.stopPropagation(); }

  applyBtn.addEventListener('click', emit);
  camSelect.addEventListener('change', emit);
  hostInput.addEventListener('keydown', onKey);
  portInput.addEventListener('keydown', onKey);
  wInput.addEventListener('keydown', onKey);
  hInput.addEventListener('keydown', onKey);
  root.addEventListener('pointerdown', stopProp);
  root.addEventListener('mousedown', stopProp);

  return function cleanup() {
    applyBtn.removeEventListener('click', emit);
    camSelect.removeEventListener('change', emit);
    hostInput.removeEventListener('keydown', onKey);
    portInput.removeEventListener('keydown', onKey);
    wInput.removeEventListener('keydown', onKey);
    hInput.removeEventListener('keydown', onKey);
    root.removeEventListener('pointerdown', stopProp);
    root.removeEventListener('mousedown', stopProp);
  };
}
