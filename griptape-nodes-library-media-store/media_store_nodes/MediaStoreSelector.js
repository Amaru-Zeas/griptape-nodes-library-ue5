/**
 * MediaStoreSelector
 * Dropdown for choosing key saved by Media Store Set nodes.
 */
export default function MediaStoreSelector(container, props) {
  const { value, onChange, disabled } = props;
  const v = value && typeof value === "object" ? value : {};
  const keys = Array.isArray(v.keys) ? v.keys : [];
  const selectedKey = (v.selectedKey || "").trim();
  const mediaType = v.mediaType || "";
  const preview = v.preview || "";
  const refreshTick = Number.isFinite(v.refreshTick) ? v.refreshTick : 0;

  const options = keys
    .map((k) => {
      const sel = k === selectedKey ? " selected" : "";
      return '<option value="' + k + '"' + sel + ">" + k + "</option>";
    })
    .join("");

  container.innerHTML =
    '<div class="ms-selector nodrag nowheel" style="display:flex;flex-direction:column;gap:6px;padding:6px;background:#121212;border-radius:6px;">' +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<label style="font-size:12px;color:#bbb;">Set node</label>' +
        '<select class="key-select" style="flex:1;background:#1f1f1f;color:#ddd;border:1px solid #333;padding:5px;border-radius:4px;" ' + (disabled ? "disabled" : "") + ">" +
          (options || '<option value="">(none)</option>') +
        "</select>" +
        '<button class="btn-refresh" style="min-width:84px;padding:6px 12px;font-size:12px;background:#2a2a4a;border:1px solid #444;border-radius:4px;color:#ccc;cursor:pointer;" ' + (disabled ? "disabled" : "") + ">Refresh</button>" +
      "</div>" +
      '<div style="font-size:11px;color:#c8c8c8;">Name: ' + (selectedKey || "-") + ' | Type: ' + (mediaType || "-") + "</div>" +
      '<div style="font-size:11px;color:#8a8a8a;max-height:54px;overflow:auto;border:1px solid #272727;padding:4px;border-radius:4px;background:#0f0f0f;">' +
        (preview || "(preview empty)") +
      "</div>" +
    "</div>";

  const root = container.querySelector(".ms-selector");
  const keySelect = container.querySelector(".key-select");
  const refreshBtn = container.querySelector(".btn-refresh");

  function emit(nextRefreshTick) {
    if (!onChange) return;
    onChange({
      keys: keys,
      selectedKey: (keySelect.value || "").trim(),
      mediaType: mediaType,
      preview: preview,
      refreshTick: nextRefreshTick
    });
  }

  function handleRefresh(e) {
    e.stopPropagation();
    e.preventDefault();
    emit(refreshTick + 1);
  }

  function handleSelectChange(e) {
    e.stopPropagation();
    emit(refreshTick);
  }

  function stopProp(e) {
    e.stopPropagation();
  }

  refreshBtn.addEventListener("click", handleRefresh);
  keySelect.addEventListener("change", handleSelectChange);
  root.addEventListener("pointerdown", stopProp);
  root.addEventListener("mousedown", stopProp);

  return function cleanup() {
    refreshBtn.removeEventListener("click", handleRefresh);
    keySelect.removeEventListener("change", handleSelectChange);
    root.removeEventListener("pointerdown", stopProp);
    root.removeEventListener("mousedown", stopProp);
  };
}

