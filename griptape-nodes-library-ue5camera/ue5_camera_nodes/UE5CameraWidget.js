/**
 * UE5CameraWidget - Live UE5 viewport + interactive camera controls.
 *
 * Embeds a Pixel Streaming video feed from UE5 so you see exactly what
 * the camera sees, and navigate it in real-time from inside Griptape Nodes.
 *
 * Requirements in UE5:
 *   1. "Pixel Streaming" plugin enabled (for the live viewport)
 *   2. "Remote Control API" plugin enabled (for camera position control)
 *   3. "Editor Scripting Utilities" plugin enabled (for viewport mode)
 *   4. CORS enabled: Project Settings > Plugins > Web Remote Control
 */

export default function UE5CameraWidget(container, props) {
  var value = props.value;
  var onChange = props.onChange;
  var disabled = props.disabled;
  var widgetHeight = (props.height && props.height > 0) ? Math.max(500, props.height - 40) : 600;

  // -------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------
  var state = {
    host: 'localhost',
    port: 30010,
    streamUrl: 'http://127.0.0.1',
    mode: 'viewport',
    actorPath: '',
    posX: 0, posY: 0, posZ: 200,
    rotPitch: 0, rotYaw: 0, rotRoll: 0,
    step: 100,
    rotStep: 15,
    connected: false,
    streamLoaded: false,
    statusMsg: 'Enter Pixel Streaming URL and click Load'
  };

  if (value && typeof value === 'object') {
    if (value.host !== undefined) state.host = value.host;
    if (value.port !== undefined) state.port = Number(value.port);
    if (value.streamUrl !== undefined) state.streamUrl = value.streamUrl;
    if (value.mode !== undefined) state.mode = value.mode;
    if (value.actorPath !== undefined) state.actorPath = value.actorPath;
    if (value.posX !== undefined) state.posX = Number(value.posX);
    if (value.posY !== undefined) state.posY = Number(value.posY);
    if (value.posZ !== undefined) state.posZ = Number(value.posZ);
    if (value.rotPitch !== undefined) state.rotPitch = Number(value.rotPitch);
    if (value.rotYaw !== undefined) state.rotYaw = Number(value.rotYaw);
    if (value.rotRoll !== undefined) state.rotRoll = Number(value.rotRoll);
    if (value.step !== undefined) state.step = Number(value.step);
    if (value.rotStep !== undefined) state.rotStep = Number(value.rotStep);
  }

  var viewportH = Math.max(280, widgetHeight - 320);

  // -------------------------------------------------------------------
  // Build DOM
  // -------------------------------------------------------------------
  container.innerHTML =
    '<div class="ue5cam nodrag nowheel" style="' +
      'display:flex;flex-direction:column;gap:0;padding:0;' +
      'background:#0d0d1a;border-radius:8px;user-select:none;' +
      'width:100%;box-sizing:border-box;font-family:monospace;font-size:11px;color:#ccc;' +
      'overflow:hidden;">' +

      // ── Live Viewport ──
      '<div class="vp-area" style="' +
        'width:100%;height:' + viewportH + 'px;background:#000;position:relative;overflow:hidden;">' +

        // Placeholder when no stream
        '<div class="vp-placeholder" style="' +
          'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
          'height:100%;color:#555;gap:8px;text-align:center;padding:20px;">' +
          '<div style="font-size:36px;">&#127909;</div>' +
          '<div style="font-size:13px;color:#888;">UE5 Live Viewport</div>' +
          '<div style="font-size:10px;max-width:300px;">Enable <b>Pixel Streaming</b> in UE5, ' +
          'start the signaling server, then enter the stream URL below and click <b>Load Stream</b>.</div>' +
        '</div>' +

        // Stream iframe (hidden until loaded)
        '<iframe class="vp-iframe" style="' +
          'width:100%;height:100%;border:none;display:none;position:absolute;top:0;left:0;" ' +
          'allow="autoplay; fullscreen; microphone; camera; xr-spatial-tracking" ' +
          'allowfullscreen></iframe>' +

      '</div>' +

      // ── Stream URL bar ──
      '<div style="display:flex;gap:3px;align-items:center;padding:6px 8px;background:#111128;border-top:1px solid #222;">' +
        '<span style="color:#666;font-size:10px;flex-shrink:0;">Stream</span>' +
        '<input class="inp-stream" type="text" value="' + state.streamUrl + '" ' +
          'placeholder="http://localhost:80" ' +
          'style="flex:1;padding:4px 6px;font-size:11px;background:#0a0a1e;border:1px solid #333;' +
          'border-radius:3px;color:#adf;outline:none;font-family:monospace;" />' +
        '<button class="btn-stream" style="' +
          'padding:4px 10px;font-size:10px;border-radius:3px;cursor:pointer;' +
          'font-weight:bold;border:1px solid #2a6bba;background:#1a4b8a;color:#fff;">Load Stream</button>' +
      '</div>' +

      // ── Controls panel (collapsible) ──
      '<div class="ctrl-panel" style="padding:6px 8px;background:#0f0f23;border-top:1px solid #1a1a33;">' +

        // Connection + mode row
        '<div style="display:flex;gap:3px;align-items:center;margin-bottom:4px;">' +
          '<span class="conn-dot" style="width:7px;height:7px;border-radius:50%;background:#666;flex-shrink:0;"></span>' +
          '<input class="inp-host" type="text" value="' + state.host + '" ' +
            'style="width:80px;padding:3px 5px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
            'border-radius:3px;color:#ddd;outline:none;font-family:monospace;" />' +
          '<span style="color:#444;">:</span>' +
          '<input class="inp-port" type="number" value="' + state.port + '" ' +
            'style="width:50px;padding:3px 5px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
            'border-radius:3px;color:#ddd;outline:none;font-family:monospace;" />' +
          '<select class="sel-mode" style="padding:3px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
            'border-radius:3px;color:#ddd;outline:none;font-family:monospace;">' +
            '<option value="viewport"' + (state.mode === 'viewport' ? ' selected' : '') + '>Viewport</option>' +
            '<option value="actor"' + (state.mode === 'actor' ? ' selected' : '') + '>Actor</option>' +
          '</select>' +
          '<input class="inp-actor" type="text" value="' + state.actorPath + '" ' +
            'placeholder="Actor path..." ' +
            'style="flex:1;padding:3px 5px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
            'border-radius:3px;color:#ddd;outline:none;font-family:monospace;' +
            (state.mode === 'viewport' ? 'opacity:0.3;' : '') + '" />' +
          '<button class="btn-connect" style="' +
            'padding:3px 8px;font-size:10px;border-radius:3px;cursor:pointer;' +
            'border:1px solid #444;background:#252540;color:#ccc;">Test</button>' +
        '</div>' +

        // Position + Rotation + Nav in a row
        '<div style="display:flex;gap:8px;align-items:start;">' +

          // Left: Position & Rotation
          '<div style="flex:1;display:flex;flex-direction:column;gap:3px;">' +
            // Position
            '<div style="display:flex;gap:2px;align-items:center;">' +
              '<span style="font-size:9px;color:#666;width:18px;">Pos</span>' +
              '<span style="font-size:9px;color:#e55;width:10px;">X</span>' +
              '<input class="inp-px" type="number" step="10" value="' + state.posX.toFixed(1) + '" ' +
                'style="flex:1;padding:2px 4px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
                'border-radius:2px;color:#ddd;outline:none;font-family:monospace;min-width:0;" />' +
              '<span style="font-size:9px;color:#5e5;width:10px;">Y</span>' +
              '<input class="inp-py" type="number" step="10" value="' + state.posY.toFixed(1) + '" ' +
                'style="flex:1;padding:2px 4px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
                'border-radius:2px;color:#ddd;outline:none;font-family:monospace;min-width:0;" />' +
              '<span style="font-size:9px;color:#55e;width:10px;">Z</span>' +
              '<input class="inp-pz" type="number" step="10" value="' + state.posZ.toFixed(1) + '" ' +
                'style="flex:1;padding:2px 4px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
                'border-radius:2px;color:#ddd;outline:none;font-family:monospace;min-width:0;" />' +
            '</div>' +
            // Rotation
            '<div style="display:flex;gap:2px;align-items:center;">' +
              '<span style="font-size:9px;color:#666;width:18px;">Rot</span>' +
              '<span style="font-size:9px;color:#ccc;width:10px;">P</span>' +
              '<input class="inp-rp" type="number" step="5" value="' + state.rotPitch.toFixed(1) + '" ' +
                'style="flex:1;padding:2px 4px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
                'border-radius:2px;color:#ddd;outline:none;font-family:monospace;min-width:0;" />' +
              '<span style="font-size:9px;color:#ccc;width:10px;">Y</span>' +
              '<input class="inp-ry" type="number" step="5" value="' + state.rotYaw.toFixed(1) + '" ' +
                'style="flex:1;padding:2px 4px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
                'border-radius:2px;color:#ddd;outline:none;font-family:monospace;min-width:0;" />' +
              '<span style="font-size:9px;color:#ccc;width:10px;">R</span>' +
              '<input class="inp-rr" type="number" step="5" value="' + state.rotRoll.toFixed(1) + '" ' +
                'style="flex:1;padding:2px 4px;font-size:10px;background:#0a0a1e;border:1px solid #333;' +
                'border-radius:2px;color:#ddd;outline:none;font-family:monospace;min-width:0;" />' +
            '</div>' +
            // Action buttons
            '<div style="display:flex;gap:3px;">' +
              '<button class="btn-get" style="flex:1;padding:3px;font-size:10px;border-radius:3px;cursor:pointer;' +
                'border:1px solid #2a6bba;background:#1a4b8a;color:#fff;font-weight:bold;">Sync from UE5</button>' +
              '<button class="btn-set" style="flex:1;padding:3px;font-size:10px;border-radius:3px;cursor:pointer;' +
                'border:1px solid #2a8b4a;background:#1a6b3a;color:#fff;font-weight:bold;">Push to UE5</button>' +
            '</div>' +
          '</div>' +

          // Right: Navigation controls
          '<div style="display:flex;flex-direction:column;gap:2px;align-items:center;">' +
            // Movement grid
            '<div style="display:grid;grid-template-columns:28px 28px 28px;gap:1px;">' +
              '<div></div>' +
              '<button class="nav-fwd" style="width:28px;height:22px;font-size:11px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#ccc;display:flex;align-items:center;justify-content:center;" title="Forward">&#9650;</button>' +
              '<button class="nav-up" style="width:28px;height:22px;font-size:9px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#8cf;display:flex;align-items:center;justify-content:center;" title="Up +Z">&#8679;</button>' +

              '<button class="nav-left" style="width:28px;height:22px;font-size:11px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#ccc;display:flex;align-items:center;justify-content:center;" title="Strafe Left">&#9664;</button>' +
              '<button class="nav-right" style="width:28px;height:22px;font-size:11px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#ccc;display:flex;align-items:center;justify-content:center;" title="Strafe Right">&#9654;</button>' +
              '<button class="nav-down" style="width:28px;height:22px;font-size:9px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#8cf;display:flex;align-items:center;justify-content:center;" title="Down -Z">&#8681;</button>' +

              '<button class="nav-rotl" style="width:28px;height:22px;font-size:10px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#fc8;display:flex;align-items:center;justify-content:center;" title="Yaw Left">&#8630;</button>' +
              '<button class="nav-back" style="width:28px;height:22px;font-size:11px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#ccc;display:flex;align-items:center;justify-content:center;" title="Backward">&#9660;</button>' +
              '<button class="nav-rotr" style="width:28px;height:22px;font-size:10px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#fc8;display:flex;align-items:center;justify-content:center;" title="Yaw Right">&#8631;</button>' +
            '</div>' +
            // Pitch + Step
            '<div style="display:flex;gap:1px;">' +
              '<button class="nav-pitchu" style="width:28px;height:20px;font-size:8px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#fc8;display:flex;align-items:center;justify-content:center;" title="Pitch Up">P+</button>' +
              '<button class="nav-pitchd" style="width:28px;height:20px;font-size:8px;border-radius:2px;cursor:pointer;border:1px solid #444;background:#252540;color:#fc8;display:flex;align-items:center;justify-content:center;" title="Pitch Down">P-</button>' +
              '<input class="inp-step" type="number" value="' + state.step + '" title="Move step size" ' +
                'style="width:36px;padding:2px;font-size:9px;background:#0a0a1e;border:1px solid #333;' +
                'border-radius:2px;color:#ddd;outline:none;font-family:monospace;text-align:center;" />' +
            '</div>' +
          '</div>' +

        '</div>' +

      '</div>' +

      // ── Status bar ──
      '<div class="status-bar" style="padding:3px 8px;font-size:9px;color:#666;background:#0a0a14;' +
        'border-top:1px solid #1a1a33;text-align:center;">' + state.statusMsg + '</div>' +

    '</div>';

  // -------------------------------------------------------------------
  // DOM References
  // -------------------------------------------------------------------
  var widget = container.querySelector('.ue5cam');
  var vpArea = container.querySelector('.vp-area');
  var vpPlaceholder = container.querySelector('.vp-placeholder');
  var vpIframe = container.querySelector('.vp-iframe');
  var inpStream = container.querySelector('.inp-stream');
  var btnStream = container.querySelector('.btn-stream');
  var connDot = container.querySelector('.conn-dot');
  var inpHost = container.querySelector('.inp-host');
  var inpPort = container.querySelector('.inp-port');
  var selMode = container.querySelector('.sel-mode');
  var inpActor = container.querySelector('.inp-actor');
  var btnConnect = container.querySelector('.btn-connect');
  var inpPx = container.querySelector('.inp-px');
  var inpPy = container.querySelector('.inp-py');
  var inpPz = container.querySelector('.inp-pz');
  var inpRp = container.querySelector('.inp-rp');
  var inpRy = container.querySelector('.inp-ry');
  var inpRr = container.querySelector('.inp-rr');
  var inpStep = container.querySelector('.inp-step');
  var btnGet = container.querySelector('.btn-get');
  var btnSet = container.querySelector('.btn-set');
  var statusBar = container.querySelector('.status-bar');

  var navFwd = container.querySelector('.nav-fwd');
  var navBack = container.querySelector('.nav-back');
  var navLeft = container.querySelector('.nav-left');
  var navRight = container.querySelector('.nav-right');
  var navUp = container.querySelector('.nav-up');
  var navDown = container.querySelector('.nav-down');
  var navRotL = container.querySelector('.nav-rotl');
  var navRotR = container.querySelector('.nav-rotr');
  var navPitchU = container.querySelector('.nav-pitchu');
  var navPitchD = container.querySelector('.nav-pitchd');

  // -------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------

  function baseUrl() {
    return 'http://' + state.host + ':' + state.port;
  }

  function setStatus(msg, isError) {
    state.statusMsg = msg;
    if (statusBar) {
      statusBar.textContent = msg;
      statusBar.style.color = isError ? '#e55' : '#666';
    }
  }

  function setConnected(ok) {
    state.connected = ok;
    connDot.style.background = ok ? '#4e4' : '#e44';
  }

  function readInputs() {
    state.host = inpHost.value.trim() || 'localhost';
    state.port = parseInt(inpPort.value, 10) || 30010;
    state.streamUrl = inpStream.value.trim();
    state.mode = selMode.value;
    state.actorPath = inpActor.value.trim();
    state.posX = parseFloat(inpPx.value) || 0;
    state.posY = parseFloat(inpPy.value) || 0;
    state.posZ = parseFloat(inpPz.value) || 0;
    state.rotPitch = parseFloat(inpRp.value) || 0;
    state.rotYaw = parseFloat(inpRy.value) || 0;
    state.rotRoll = parseFloat(inpRr.value) || 0;
    state.step = parseFloat(inpStep.value) || 100;
  }

  function updateUI() {
    inpPx.value = state.posX.toFixed(1);
    inpPy.value = state.posY.toFixed(1);
    inpPz.value = state.posZ.toFixed(1);
    inpRp.value = state.rotPitch.toFixed(1);
    inpRy.value = state.rotYaw.toFixed(1);
    inpRr.value = state.rotRoll.toFixed(1);
    inpActor.style.opacity = state.mode === 'viewport' ? '0.3' : '1';
  }

  function syncToNode() {
    if (!onChange) return;
    onChange({
      host: state.host,
      port: state.port,
      streamUrl: state.streamUrl,
      mode: state.mode,
      actorPath: state.actorPath,
      posX: state.posX, posY: state.posY, posZ: state.posZ,
      rotPitch: state.rotPitch, rotYaw: state.rotYaw, rotRoll: state.rotRoll,
      step: state.step, rotStep: state.rotStep,
    });
  }

  // -------------------------------------------------------------------
  // Pixel Streaming - load the live viewport
  // -------------------------------------------------------------------

  function loadStream() {
    readInputs();
    var url = state.streamUrl;
    if (!url) {
      setStatus('Enter a Pixel Streaming URL first', true);
      return;
    }

    setStatus('Loading stream from ' + url + '...', false);

    vpIframe.src = url;
    vpIframe.style.display = 'block';
    vpPlaceholder.style.display = 'none';
    state.streamLoaded = true;

    vpIframe.onload = function() {
      setStatus('Stream loaded: ' + url, false);
    };
    vpIframe.onerror = function() {
      setStatus('Failed to load stream. Check URL and Pixel Streaming setup.', true);
    };

    syncToNode();
  }

  // Auto-load if we already have a non-default stream URL from saved state
  if (state.streamUrl && state.streamUrl !== 'http://127.0.0.1' && state.streamUrl !== 'http://localhost:80') {
    setTimeout(loadStream, 300);
  }

  // -------------------------------------------------------------------
  // UE5 Remote Control API calls
  // -------------------------------------------------------------------

  var EDITOR_LIB = '/Script/EditorScriptingUtilities.Default__EditorLevelLibrary';

  function callUE5(objectPath, functionName, parameters) {
    return fetch(baseUrl() + '/remote/object/call', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        objectPath: objectPath,
        functionName: functionName,
        parameters: parameters || {},
        generateTransaction: false
      })
    }).then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function testConnection() {
    readInputs();
    setStatus('Testing connection...', false);
    fetch(baseUrl() + '/remote/info', { method: 'GET' })
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function(info) {
        setConnected(true);
        setStatus('Connected to UE5 v' + (info.EngineVersion || '?'), false);
      })
      .catch(function(err) {
        setConnected(false);
        setStatus('Connection failed: ' + err.message, true);
      });
  }

  function getCameraFromUE5() {
    readInputs();
    setStatus('Reading camera...', false);

    var promise;
    if (state.mode === 'viewport') {
      promise = callUE5(EDITOR_LIB, 'GetLevelViewportCameraInfo', {});
    } else {
      if (!state.actorPath) { setStatus('Actor path required', true); return; }
      promise = Promise.all([
        callUE5(state.actorPath, 'K2_GetActorLocation'),
        callUE5(state.actorPath, 'K2_GetActorRotation')
      ]).then(function(r) {
        return { CameraLocation: r[0].ReturnValue || {}, CameraRotation: r[1].ReturnValue || {} };
      });
    }

    promise.then(function(result) {
      var loc = result.CameraLocation || {};
      var rot = result.CameraRotation || {};
      state.posX = loc.X || 0;
      state.posY = loc.Y || 0;
      state.posZ = loc.Z || 0;
      state.rotPitch = rot.Pitch || 0;
      state.rotYaw = rot.Yaw || 0;
      state.rotRoll = rot.Roll || 0;
      updateUI();
      syncToNode();
      setConnected(true);
      setStatus('Synced (' + state.posX.toFixed(0) + ', ' + state.posY.toFixed(0) + ', ' + state.posZ.toFixed(0) + ')', false);
    }).catch(function(err) {
      setStatus('Get failed: ' + err.message, true);
    });
  }

  function pushCameraToUE5() {
    readInputs();
    setStatus('Pushing camera...', false);

    var promise;
    if (state.mode === 'viewport') {
      promise = callUE5(EDITOR_LIB, 'SetLevelViewportCameraInfo', {
        CameraLocation: { X: state.posX, Y: state.posY, Z: state.posZ },
        CameraRotation: { Pitch: state.rotPitch, Yaw: state.rotYaw, Roll: state.rotRoll }
      });
    } else {
      if (!state.actorPath) { setStatus('Actor path required', true); return; }
      promise = callUE5(state.actorPath, 'K2_SetActorLocation', {
        NewLocation: { X: state.posX, Y: state.posY, Z: state.posZ },
        bSweep: false, SweepHitResult: {}, bTeleport: true
      }).then(function() {
        return callUE5(state.actorPath, 'K2_SetActorRotation', {
          NewRotation: { Pitch: state.rotPitch, Yaw: state.rotYaw, Roll: state.rotRoll },
          bTeleportPhysics: true
        });
      });
    }

    promise.then(function() {
      setConnected(true);
      setStatus('Set (' + state.posX.toFixed(0) + ', ' + state.posY.toFixed(0) + ', ' + state.posZ.toFixed(0) + ')', false);
      syncToNode();
    }).catch(function(err) {
      setStatus('Push failed: ' + err.message, true);
    });
  }

  // -------------------------------------------------------------------
  // Navigation
  // -------------------------------------------------------------------

  function navigate(direction) {
    readInputs();
    var yawRad = state.rotYaw * Math.PI / 180;
    var step = state.step;
    var rStep = state.rotStep;
    var fx = Math.cos(yawRad), fy = Math.sin(yawRad);
    var rx = -Math.sin(yawRad), ry = Math.cos(yawRad);

    switch (direction) {
      case 'fwd':   state.posX += fx * step; state.posY += fy * step; break;
      case 'back':  state.posX -= fx * step; state.posY -= fy * step; break;
      case 'left':  state.posX -= rx * step; state.posY -= ry * step; break;
      case 'right': state.posX += rx * step; state.posY += ry * step; break;
      case 'up':    state.posZ += step; break;
      case 'down':  state.posZ -= step; break;
      case 'rotL':  state.rotYaw += rStep; break;
      case 'rotR':  state.rotYaw -= rStep; break;
      case 'pitU':  state.rotPitch = Math.min(89, state.rotPitch + rStep); break;
      case 'pitD':  state.rotPitch = Math.max(-89, state.rotPitch - rStep); break;
    }

    updateUI();
    if (state.connected) {
      pushCameraToUE5();
    } else {
      syncToNode();
    }
  }

  // -------------------------------------------------------------------
  // Events
  // -------------------------------------------------------------------

  function stop(e) { e.stopPropagation(); }
  function stopAll(e) { e.stopPropagation(); e.preventDefault(); }

  btnStream.addEventListener('click', function(e) { stopAll(e); loadStream(); });
  btnConnect.addEventListener('click', function(e) { stopAll(e); testConnection(); });
  btnGet.addEventListener('click', function(e) { stopAll(e); getCameraFromUE5(); });
  btnSet.addEventListener('click', function(e) { stopAll(e); pushCameraToUE5(); });

  selMode.addEventListener('change', function(e) {
    stop(e); state.mode = selMode.value;
    inpActor.style.opacity = state.mode === 'viewport' ? '0.3' : '1';
    syncToNode();
  });

  // Enter key in stream URL loads the stream
  inpStream.addEventListener('keydown', function(e) {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); loadStream(); }
  });

  var allInputs = [inpHost, inpPort, inpStream, inpActor,
                   inpPx, inpPy, inpPz, inpRp, inpRy, inpRr, inpStep];
  allInputs.forEach(function(inp) {
    inp.addEventListener('change', function(e) { stop(e); readInputs(); syncToNode(); });
    inp.addEventListener('keydown', stop);
    inp.addEventListener('keyup', stop);
    inp.addEventListener('input', stop);
  });

  var navMap = [
    [navFwd, 'fwd'], [navBack, 'back'], [navLeft, 'left'], [navRight, 'right'],
    [navUp, 'up'], [navDown, 'down'],
    [navRotL, 'rotL'], [navRotR, 'rotR'],
    [navPitchU, 'pitU'], [navPitchD, 'pitD'],
  ];
  navMap.forEach(function(pair) {
    pair[0].addEventListener('click', function(e) { stopAll(e); navigate(pair[1]); });
  });

  widget.addEventListener('pointerdown', stop);
  widget.addEventListener('mousedown', stop);

  // -------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------
  return function() {
    if (vpIframe) vpIframe.src = '';
  };
}
