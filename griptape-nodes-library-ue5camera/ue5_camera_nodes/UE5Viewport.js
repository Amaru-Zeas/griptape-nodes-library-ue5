/**
 * UE5Viewport - Live UE5 viewport + screenshot capture.
 *
 * The single button toggles between Load (stream URL) and Capture (screenshot).
 * Screenshot opens a temporary WebRTC connection to grab a video frame.
 */

export default function UE5Viewport(container, props) {
  var value = props.value;
  var onChange = props.onChange;
  var disabled = props.disabled;
  var viewportH = (props.height && props.height > 0) ? Math.max(300, props.height - 60) : 450;

  var url = '';
  if (value && typeof value === 'object') {
    url = value.url || '';
  } else if (typeof value === 'string') {
    url = value;
  }
  url = url.trim();

  var streamLoaded = !!url;

  container.innerHTML =
    '<div class="ue5vp nodrag nowheel" style="' +
      'display:flex;flex-direction:column;gap:0;' +
      'background:#000;border-radius:6px;user-select:none;' +
      'width:100%;box-sizing:border-box;overflow:hidden;">' +

      '<div class="vp-area" style="width:100%;height:' + viewportH + 'px;position:relative;background:#000;">' +
        '<div class="vp-empty" style="' +
          'display:' + (url ? 'none' : 'flex') + ';' +
          'flex-direction:column;align-items:center;justify-content:center;' +
          'height:100%;color:#555;gap:8px;text-align:center;padding:20px;">' +
          '<div style="font-size:40px;">&#127909;</div>' +
          '<div style="font-size:14px;color:#999;">UE5 Viewport</div>' +
          '<div style="font-size:11px;color:#666;max-width:280px;">' +
            'In UE5: Pixel Streaming toolbar &gt; Stream Level Editor<br>' +
            'Then enter the URL below and click Load</div>' +
        '</div>' +
        '<iframe class="vp-frame" ' +
          (url ? 'src="' + url + '"' : '') +
          ' style="width:100%;height:100%;border:none;' +
          'display:' + (url ? 'block' : 'none') + ';position:absolute;top:0;left:0;" ' +
          'allow="autoplay; fullscreen; microphone; camera; xr-spatial-tracking" ' +
          'allowfullscreen></iframe>' +
        '<div class="vp-flash" style="position:absolute;top:0;left:0;width:100%;height:100%;' +
          'background:#fff;opacity:0;pointer-events:none;transition:opacity 0.15s;"></div>' +
      '</div>' +

      '<div style="display:flex;gap:3px;padding:6px 8px;background:#111;border-top:1px solid #222;">' +
        '<input class="url-inp" type="text" value="' + url + '" placeholder="http://127.0.0.1" ' +
          'style="flex:1;padding:5px 8px;font-size:12px;background:#1a1a1a;border:1px solid #333;' +
          'border-radius:4px;color:#adf;outline:none;font-family:monospace;min-width:0;" />' +
        '<button class="btn-action" style="padding:5px 14px;font-size:12px;' +
          'border:1px solid ' + (streamLoaded ? '#ba5a2a' : '#2a6bba') + ';' +
          'background:' + (streamLoaded ? '#8a3a1a' : '#1a4b8a') + ';' +
          'border-radius:4px;color:#fff;cursor:pointer;font-weight:bold;' +
          'flex-shrink:0;">' + (streamLoaded ? '&#128247; Capture' : 'Load') + '</button>' +
      '</div>' +

      '<div class="status-bar" style="padding:2px 8px;font-size:10px;color:#888;background:#0a0a0a;' +
        'text-align:center;min-height:14px;">' +
        (streamLoaded ? 'Click Capture to screenshot. Shift+click to reload stream.' : '') +
      '</div>' +

    '</div>';

  var widget = container.querySelector('.ue5vp');
  var vpEmpty = container.querySelector('.vp-empty');
  var vpFrame = container.querySelector('.vp-frame');
  var vpFlash = container.querySelector('.vp-flash');
  var urlInp = container.querySelector('.url-inp');
  var btnAction = container.querySelector('.btn-action');
  var statusBar = container.querySelector('.status-bar');

  var currentUrl = url;

  function setStatus(msg) { if (statusBar) statusBar.textContent = msg; }

  function setButtonMode(mode) {
    if (mode === 'capture') {
      streamLoaded = true;
      btnAction.innerHTML = '&#128247; Capture';
      btnAction.style.background = '#8a3a1a';
      btnAction.style.borderColor = '#ba5a2a';
      setStatus('Click Capture to screenshot. Shift+click to reload stream.');
    } else {
      streamLoaded = false;
      btnAction.textContent = 'Load';
      btnAction.style.background = '#1a4b8a';
      btnAction.style.borderColor = '#2a6bba';
      setStatus('');
    }
  }

  function loadUrl() {
    var u = urlInp.value.trim();
    if (!u) return;
    currentUrl = u;
    vpFrame.src = u;
    vpFrame.style.display = 'block';
    vpEmpty.style.display = 'none';
    setButtonMode('capture');
    if (onChange) onChange({ url: u, screenshot: '' });
  }

  function flash() {
    vpFlash.style.opacity = '0.6';
    setTimeout(function() { vpFlash.style.opacity = '0'; }, 150);
  }

  // ── Screenshot via WebRTC ──
  function takeScreenshot() {
    if (!currentUrl) { setStatus('Load a stream first'); return; }

    setStatus('Capturing...');
    btnAction.style.opacity = '0.5';
    btnAction.disabled = true;

    var wsUrl = currentUrl.replace(/^http/, 'ws');
    var ws, pc, videoEl, timeout;

    function cleanup() {
      clearTimeout(timeout);
      if (pc) try { pc.close(); } catch(e) {}
      if (ws && ws.readyState < 2) try { ws.close(); } catch(e) {}
      pc = null; ws = null;
      btnAction.style.opacity = '1';
      btnAction.disabled = false;
    }

    function captureFrame() {
      try {
        var w = videoEl.videoWidth || 1920;
        var h = videoEl.videoHeight || 1080;
        var canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        canvas.getContext('2d').drawImage(videoEl, 0, 0, w, h);
        var dataUrl = canvas.toDataURL('image/png');
        flash();
        setStatus('Captured ' + w + 'x' + h + ' - run flow to get image output');
        if (onChange) onChange({ url: currentUrl, screenshot: dataUrl });
      } catch(e) {
        setStatus('Capture failed: ' + e.message);
      }
      cleanup();
    }

    function setupPC(iceServers) {
      pc = new RTCPeerConnection({ iceServers: iceServers || [] });
      videoEl = document.createElement('video');
      videoEl.autoplay = true;
      videoEl.playsInline = true;
      videoEl.muted = true;

      pc.ontrack = function(ev) {
        videoEl.srcObject = ev.streams[0] || new MediaStream([ev.track]);
        videoEl.onloadeddata = function() {
          setTimeout(captureFrame, 300);
        };
      };

      pc.onicecandidate = function(ev) {
        if (ev.candidate && ws && ws.readyState === 1) {
          ws.send(JSON.stringify({ type: 'iceCandidate', candidate: ev.candidate }));
        }
      };
    }

    function handleOffer(sdp) {
      if (!pc) return;
      var desc = { type: 'offer', sdp: typeof sdp === 'string' ? sdp : sdp.sdp };
      pc.setRemoteDescription(new RTCSessionDescription(desc))
        .then(function() { return pc.createAnswer(); })
        .then(function(answer) {
          pc.setLocalDescription(answer);
          if (ws && ws.readyState === 1) {
            ws.send(JSON.stringify({ type: 'answer', sdp: answer.sdp }));
          }
        })
        .catch(function(e) {
          setStatus('WebRTC error: ' + e.message);
          cleanup();
        });
    }

    try {
      ws = new WebSocket(wsUrl);
    } catch(e) {
      setStatus('Cannot connect to signalling server');
      cleanup();
      return;
    }

    ws.onopen = function() {
      ws.send(JSON.stringify({ type: 'listStreamers' }));
    };

    ws.onmessage = function(ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch(e) { return; }

      switch (msg.type) {
        case 'config':
          var ice = [];
          if (msg.peerConnectionOptions && msg.peerConnectionOptions.iceServers) {
            ice = msg.peerConnectionOptions.iceServers;
          }
          setupPC(ice);
          break;

        case 'streamerList':
          var sid = (msg.ids && msg.ids.length) ? msg.ids[0] : 'DefaultStreamer';
          ws.send(JSON.stringify({ type: 'subscribe', streamerId: sid }));
          break;

        case 'offer':
          if (!pc) setupPC([]);
          handleOffer(msg.sdp || msg);
          break;

        case 'iceCandidate':
          if (pc && msg.candidate) {
            try {
              var c = typeof msg.candidate === 'string' ? JSON.parse(msg.candidate) : msg.candidate;
              pc.addIceCandidate(new RTCIceCandidate(c));
            } catch(e) {}
          }
          break;
      }
    };

    ws.onerror = function() {
      setStatus('Cannot reach signalling server at ' + wsUrl);
      cleanup();
    };

    ws.onclose = function() {
      if (pc && !videoEl.videoWidth) {
        setStatus('Connection closed before capture');
        cleanup();
      }
    };

    timeout = setTimeout(function() {
      setStatus('Timed out (10s). Is Pixel Streaming active?');
      cleanup();
    }, 10000);
  }

  // ── Events ──
  function stop(e) { e.stopPropagation(); }

  btnAction.addEventListener('click', function(e) {
    e.stopPropagation();
    e.preventDefault();
    if (streamLoaded && !e.shiftKey) {
      takeScreenshot();
    } else {
      loadUrl();
    }
  });

  urlInp.addEventListener('keydown', function(e) {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); loadUrl(); }
  });
  urlInp.addEventListener('keyup', stop);
  urlInp.addEventListener('input', stop);
  widget.addEventListener('pointerdown', stop);
  widget.addEventListener('mousedown', stop);

  return function() {
    if (vpFrame) vpFrame.src = '';
  };
}
