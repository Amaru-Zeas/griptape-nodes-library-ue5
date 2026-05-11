export default function StoryPromptPickerWidget(container, props) {
  var value = props.value;
  var onChange = props.onChange;
  var disabled = props.disabled;
  var widgetHeight = (props.height && props.height > 0) ? Math.max(360, props.height - 24) : 420;

  var state = {
    apiBaseUrl: "http://localhost:3000",
    promptsEndpoint: "/api/prompts",
    projectId: "",
    limit: 20,
    selectedPromptId: "",
    selectedPromptLabel: "",
    selectedPromptText: "",
    items: [],
    statusMessage: "Set project ID and click Update.",
    refreshNonce: 0,
    autoFetchOnOpen: false,
    _autoFetched: false
  };

  if (value && typeof value === "object") {
    if (value.apiBaseUrl !== undefined) state.apiBaseUrl = String(value.apiBaseUrl);
    if (value.promptsEndpoint !== undefined) state.promptsEndpoint = String(value.promptsEndpoint || "/api/prompts");
    if (value.projectId !== undefined) state.projectId = String(value.projectId);
    if (value.limit !== undefined) state.limit = Number(value.limit) || 20;
    if (value.selectedPromptId !== undefined) state.selectedPromptId = String(value.selectedPromptId || "");
    if (value.selectedPromptLabel !== undefined) state.selectedPromptLabel = String(value.selectedPromptLabel || "");
    if (value.selectedPromptText !== undefined) state.selectedPromptText = String(value.selectedPromptText || "");
    if (Array.isArray(value.items)) state.items = value.items.slice();
    if (value.statusMessage !== undefined) state.statusMessage = String(value.statusMessage || "");
    if (value.refreshNonce !== undefined) state.refreshNonce = Number(value.refreshNonce) || 0;
    if (value.autoFetchOnOpen !== undefined) state.autoFetchOnOpen = !!value.autoFetchOnOpen;
  }

  container.innerHTML =
    '<div class="story-picker nodrag nowheel" style="' +
      "display:flex;flex-direction:column;gap:8px;" +
      "padding:8px;background:#0e1120;border:1px solid #232946;border-radius:8px;" +
      "font-family:monospace;font-size:11px;color:#e8ecff;width:100%;box-sizing:border-box;" +
      "height:" + widgetHeight + "px;overflow:hidden;" +
    '">' +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:62px;color:#95a2cf;">API</span>' +
        '<input class="inp-base" type="text" value="' + escapeHtml(state.apiBaseUrl) + '" style="' +
          "flex:1;padding:4px 6px;background:#0b0f1b;border:1px solid #2e3656;border-radius:4px;color:#dbe4ff;outline:none;" +
        '" />' +
      "</div>" +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:62px;color:#95a2cf;">Path</span>' +
        '<input class="inp-endpoint" type="text" value="' + escapeHtml(state.promptsEndpoint) + '" style="' +
          "flex:1;padding:4px 6px;background:#0b0f1b;border:1px solid #2e3656;border-radius:4px;color:#dbe4ff;outline:none;" +
        '" />' +
      "</div>" +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:62px;color:#95a2cf;">Project</span>' +
        '<input class="inp-project" type="text" value="' + escapeHtml(state.projectId) + '" placeholder="proj_123" style="' +
          "flex:1;padding:4px 6px;background:#0b0f1b;border:1px solid #2e3656;border-radius:4px;color:#dbe4ff;outline:none;" +
        '" />' +
      "</div>" +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:62px;color:#95a2cf;">Limit</span>' +
        '<input class="inp-limit" type="number" min="1" max="100" value="' + String(state.limit) + '" style="' +
          "width:70px;padding:4px 6px;background:#0b0f1b;border:1px solid #2e3656;border-radius:4px;color:#dbe4ff;outline:none;" +
        '" />' +
        '<button class="btn-update" style="' +
          "margin-left:auto;padding:4px 12px;border-radius:4px;border:1px solid #2e75ff;" +
          "background:#2158c9;color:#fff;cursor:pointer;font-weight:bold;" +
        '">Update</button>' +
      "</div>" +
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span style="width:62px;color:#95a2cf;">Prompt</span>' +
        '<select class="sel-prompts" style="' +
          "flex:1;padding:4px 6px;background:#0b0f1b;border:1px solid #2e3656;border-radius:4px;color:#dbe4ff;outline:none;" +
        '"></select>' +
      "</div>" +
      '<textarea class="txt-prompt" readonly style="' +
        "flex:1;min-height:120px;padding:8px;background:#080b14;border:1px solid #2e3656;" +
        "border-radius:6px;color:#f0f4ff;resize:none;line-height:1.35;outline:none;" +
      '">' + escapeHtml(state.selectedPromptText) + "</textarea>" +
      '<div class="lbl-selected" style="min-height:14px;color:#92a4dd;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></div>' +
      '<div class="lbl-status" style="min-height:14px;color:#8d98c2;"></div>' +
    "</div>";

  var inpBase = container.querySelector(".inp-base");
  var inpEndpoint = container.querySelector(".inp-endpoint");
  var inpProject = container.querySelector(".inp-project");
  var inpLimit = container.querySelector(".inp-limit");
  var btnUpdate = container.querySelector(".btn-update");
  var selPrompts = container.querySelector(".sel-prompts");
  var txtPrompt = container.querySelector(".txt-prompt");
  var lblSelected = container.querySelector(".lbl-selected");
  var lblStatus = container.querySelector(".lbl-status");
  var lastSyncedPayload = null;

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function buildLabel(item) {
    if (!item || typeof item !== "object") return "(invalid prompt)";
    var entityType = String(item.entityType || "UNKNOWN").toUpperCase();
    var entityName = String(item.entityName || "Unnamed");
    var promptType = String(item.promptType || "custom");
    var createdAt = formatShortDate(item.createdAt);
    return "[" + entityType + "] " + entityName + " · " + promptType + " · " + createdAt;
  }

  function formatShortDate(value) {
    if (!value) return "unknown";
    var dt = new Date(value);
    if (isNaN(dt.getTime())) return String(value);
    var month = dt.toLocaleString("en-US", { month: "short" });
    var day = String(dt.getDate()).padStart(2, "0");
    var hour = String(dt.getHours()).padStart(2, "0");
    var minute = String(dt.getMinutes()).padStart(2, "0");
    return month + " " + day + " " + hour + ":" + minute;
  }

  function syncToNode() {
    if (!onChange) return;
    var payload = {
      apiBaseUrl: state.apiBaseUrl,
      promptsEndpoint: state.promptsEndpoint,
      projectId: state.projectId,
      limit: state.limit,
      selectedPromptId: state.selectedPromptId,
      selectedPromptLabel: state.selectedPromptLabel,
      selectedPromptText: state.selectedPromptText,
      items: state.items,
      statusMessage: state.statusMessage,
      refreshNonce: state.refreshNonce,
      autoFetchOnOpen: state.autoFetchOnOpen
    };

    var serialized = "";
    try {
      serialized = JSON.stringify(payload);
    } catch (_) {
      serialized = null;
    }
    if (serialized && serialized === lastSyncedPayload) {
      return;
    }
    lastSyncedPayload = serialized;
    onChange(payload);
  }

  function readInputs() {
    state.apiBaseUrl = (inpBase.value || "").trim() || "http://localhost:3000";
    state.promptsEndpoint = (inpEndpoint.value || "").trim() || "/api/prompts";
    state.projectId = (inpProject.value || "").trim();
    state.limit = Math.max(1, Math.min(100, parseInt(inpLimit.value || "20", 10) || 20));
    inpLimit.value = String(state.limit);
  }

  function setStatus(message, isError) {
    state.statusMessage = message || "";
    lblStatus.textContent = state.statusMessage;
    lblStatus.style.color = isError ? "#ff9aa9" : "#8d98c2";
  }

  function setSelectedItemById(id) {
    state.selectedPromptId = String(id || "");
    var selected = null;
    for (var i = 0; i < state.items.length; i += 1) {
      var candidate = state.items[i];
      if (String(candidate && candidate.id || "") === state.selectedPromptId) {
        selected = candidate;
        break;
      }
    }
    if (!selected && state.items.length > 0) {
      selected = state.items[0];
      state.selectedPromptId = String(selected.id || "");
    }

    state.selectedPromptText = selected ? String(selected.promptText || "") : "";
    state.selectedPromptLabel = selected ? buildLabel(selected) : "";
    txtPrompt.value = state.selectedPromptText;
    lblSelected.textContent = state.selectedPromptLabel;
    selPrompts.value = state.selectedPromptId;
  }

  function refreshDropdownOptions() {
    while (selPrompts.firstChild) {
      selPrompts.removeChild(selPrompts.firstChild);
    }

    if (!state.items.length) {
      var emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = "(no prompts yet)";
      selPrompts.appendChild(emptyOption);
      selPrompts.value = "";
      return;
    }

    for (var i = 0; i < state.items.length; i += 1) {
      var item = state.items[i];
      if (!item || typeof item !== "object") continue;
      var option = document.createElement("option");
      option.value = String(item.id || "");
      option.textContent = buildLabel(item);
      selPrompts.appendChild(option);
    }
    if (!state.selectedPromptId) {
      state.selectedPromptId = String(state.items[0].id || "");
    }
    selPrompts.value = state.selectedPromptId;
  }

  function fetchPrompts() {
    readInputs();
    if (!state.projectId) {
      setStatus("Project ID is required.", true);
      syncToNode();
      return;
    }
    state.refreshNonce = (Number(state.refreshNonce) || 0) + 1;
    setStatus("Refreshing prompts...", false);
    syncToNode();
  }

  function stop(e) {
    e.stopPropagation();
  }

  function stopAll(e) {
    e.stopPropagation();
    e.preventDefault();
  }

  refreshDropdownOptions();
  setSelectedItemById(state.selectedPromptId);
  setStatus(state.statusMessage, false);

  if (disabled) {
    btnUpdate.disabled = true;
    btnUpdate.style.opacity = "0.6";
    btnUpdate.style.cursor = "not-allowed";
  }

  btnUpdate.addEventListener("click", function(e) {
    stopAll(e);
    if (!disabled) fetchPrompts();
  });

  selPrompts.addEventListener("change", function(e) {
    stop(e);
    setSelectedItemById(selPrompts.value);
    syncToNode();
  });

  var inputs = [inpBase, inpEndpoint, inpProject, inpLimit];
  for (var i = 0; i < inputs.length; i += 1) {
    inputs[i].addEventListener("keydown", stop);
    inputs[i].addEventListener("keyup", stop);
    inputs[i].addEventListener("input", stop);
    inputs[i].addEventListener("change", function(e) {
      stop(e);
      readInputs();
      syncToNode();
    });
  }

  inpProject.addEventListener("keydown", function(e) {
    stop(e);
    if (e.key === "Enter" && !disabled) {
      e.preventDefault();
      fetchPrompts();
    }
  });

  if (state.autoFetchOnOpen && !state._autoFetched && state.projectId && !disabled) {
    state._autoFetched = true;
    setTimeout(fetchPrompts, 200);
  }

  return function cleanup() {
    container.innerHTML = "";
  };
}
