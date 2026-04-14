/**
 * UE5ViewportV2 – Live UE5 viewport + screenshot capture.
 *
 * Display : iframe (Pixel Streaming – full navigation / interaction).
 * Capture : disconnects iframe → WebRTC handshake following the official
 *           UE5.5 signalling protocol → grabs one video frame → reconnects iframe.
 */

export default function UE5ViewportV2(container, props) {
  var value   = props.value;
  var onChange = props.onChange;
  var viewportH = (props.height && props.height > 0)
    ? Math.max(280, props.height - 90) : 420;

  var url = '';
  if (value && typeof value === 'object') url = value.url || '';
  else if (typeof value === 'string') url = value;
  url = url.trim();

  var streamLoaded = !!url;
  var prevShot = (value && typeof value === 'object') ? (value.screenshot || '') : '';

  container.innerHTML =
    '<div class="ue5vp nodrag nowheel" style="display:flex;flex-direction:column;' +
      'background:#000;border-radius:6px;user-select:none;width:100%;box-sizing:border-box;overflow:hidden;">' +

      '<div class="vp-area" style="width:100%;height:' + viewportH +
        'px;position:relative;background:#111;">' +
        '<div class="vp-empty" style="display:' + (url ? 'none' : 'flex') +
          ';flex-direction:column;align-items:center;justify-content:center;' +
          'height:100%;color:#555;gap:8px;text-align:center;padding:20px;">' +
          '<div style="font-size:40px;">&#127909;</div>' +
          '<div style="font-size:14px;color:#999;">UE5 Viewport</div>' +
          '<div style="font-size:11px;color:#666;max-width:280px;">' +
            'In UE5 &gt; Pixel Streaming &gt; Stream Level Editor<br>' +
            'Enter URL below and click <b>Load</b></div>' +
        '</div>' +
        '<iframe class="vp-frame" ' + (url ? 'src="' + url + '"' : '') +
          ' style="width:100%;height:100%;border:none;display:' +
          (url ? 'block' : 'none') + ';position:absolute;top:0;left:0;" ' +
          'allow="autoplay;fullscreen;microphone;camera;xr-spatial-tracking" ' +
          'allowfullscreen></iframe>' +
        '<div class="vp-flash" style="position:absolute;top:0;left:0;width:100%;height:100%;' +
          'background:#fff;opacity:0;pointer-events:none;transition:opacity .15s;z-index:5;"></div>' +
      '</div>' +

      '<div style="display:flex;gap:3px;padding:6px 8px;background:#111;' +
        'border-top:1px solid #222;align-items:center;">' +
        '<input class="url-inp" type="text" value="' + url +
          '" placeholder="http://127.0.0.1" style="flex:1;padding:5px 8px;font-size:12px;' +
          'background:#1a1a1a;border:1px solid #333;border-radius:4px;color:#adf;' +
          'outline:none;font-family:monospace;min-width:0;" />' +
        '<button class="btn-action" style="padding:5px 14px;font-size:12px;border:1px solid ' +
          (streamLoaded ? '#ba5a2a' : '#2a6bba') + ';background:' +
          (streamLoaded ? '#8a3a1a' : '#1a4b8a') +
          ';border-radius:4px;color:#fff;cursor:pointer;font-weight:bold;' +
          'flex-shrink:0;white-space:nowrap;">' +
          (streamLoaded ? '&#128247; Capture' : 'Load') + '</button>' +
      '</div>' +

      '<div class="status-bar" style="padding:6px 10px;font-size:13px;color:#ffcc00;' +
        'background:#1a1a2e;text-align:center;min-height:20px;word-break:break-all;' +
        'border:1px solid #333;font-family:monospace;">' +
        (streamLoaded ? 'READY - Click Capture for screenshot. Shift+click = reload.' : 'Enter URL and click Load') +
      '</div>' +

      '<div class="thumb-area" style="display:' + (prevShot ? 'flex' : 'none') +
        ';align-items:center;gap:6px;padding:4px 8px 6px;background:#0a0a0a;' +
        'border-top:1px solid #1a1a1a;">' +
        '<img class="thumb-img" src="' + (prevShot || '') +
          '" style="max-height:60px;border:1px solid #333;border-radius:3px;" />' +
        '<span class="thumb-info" style="font-size:9px;color:#666;"></span>' +
      '</div>' +

    '</div>';

  var widget    = container.querySelector('.ue5vp');
  var vpEmpty   = container.querySelector('.vp-empty');
  var vpFrame   = container.querySelector('.vp-frame');
  var vpFlash   = container.querySelector('.vp-flash');
  var urlInp    = container.querySelector('.url-inp');
  var btnAction = container.querySelector('.btn-action');
  var statusBar = container.querySelector('.status-bar');
  var thumbArea = container.querySelector('.thumb-area');
  var thumbImg  = container.querySelector('.thumb-img');
  var thumbInfo = container.querySelector('.thumb-info');
  var currentUrl = url;

  function setStatus(msg) { if (statusBar) statusBar.textContent = msg; }

  function setBtnCapture() {
    streamLoaded = true;
    btnAction.innerHTML = '&#128247; Capture';
    btnAction.style.background = '#8a3a1a';
    btnAction.style.borderColor = '#ba5a2a';
  }
  function setBtnLoad() {
    streamLoaded = false;
    btnAction.textContent = 'Load';
    btnAction.style.background = '#1a4b8a';
    btnAction.style.borderColor = '#2a6bba';
  }

  function flash() {
    vpFlash.style.opacity = '0.6';
    setTimeout(function () { vpFlash.style.opacity = '0'; }, 150);
  }

  function showThumb(dataUrl, w, h) {
    if (!thumbImg) return;
    thumbImg.src = dataUrl;
    thumbArea.style.display = 'flex';
    var kb = Math.round(dataUrl.length * 3 / 4 / 1024);
    thumbInfo.textContent = w + ' x ' + h + '  (' + kb + ' KB)';
  }

  function loadUrl() {
    var u = urlInp.value.trim();
    if (!u) return;
    currentUrl = u;
    vpFrame.src = u;
    vpFrame.style.display = 'block';
    vpEmpty.style.display = 'none';
    setBtnCapture();
    setStatus('Stream loaded. Click Capture for screenshot. Shift+click = reload.');
    var prev = (value && typeof value === 'object' && value.screenshot) ? value.screenshot : '';
    if (onChange) onChange({ url: u, screenshot: prev });
  }

  /* ═══════════════════════════════════════════════════════════
   *  WebRTC capture – follows UE5.5 signalling protocol:
   *    1. connect ws
   *    2. RECEIVE config  → store ICE options
   *    3. RECEIVE playerCount (ignore)
   *    4. SEND   listStreamers
   *    5. RECEIVE streamerList → SEND subscribe
   *    6. RECEIVE offer       → create PC, set remote, create answer, SEND answer
   *    7. ICE candidates exchange
   *    8. ontrack → capture first video frame
   * ═══════════════════════════════════════════════════════════ */
  function doWebRTCCapture(cb) {
    var wsUrl = currentUrl.replace(/^http/, 'ws');
    var ws, pc, videoEl, timeout, fallbackTimer;
    var done = false;
    var iceOptions = [];
    var configReceived = false;

    function finish(result) {
      if (done) return;
      done = true;
      clearTimeout(timeout);
      clearTimeout(fallbackTimer);
      if (pc) try { pc.close(); } catch (e) {}
      if (ws && ws.readyState < 2) try { ws.close(); } catch (e) {}
      pc = null; ws = null;
      cb(result);
    }

    function captureFrame() {
      try {
        var w = videoEl.videoWidth  || 1920;
        var h = videoEl.videoHeight || 1080;
        var c = document.createElement('canvas');
        c.width = w; c.height = h;
        c.getContext('2d').drawImage(videoEl, 0, 0, w, h);
        setStatus('Encoding PNG...');
        var dataUrl = c.toDataURL('image/png');
        finish({ dataUrl: dataUrl, width: w, height: h });
      } catch (e) {
        finish({ error: 'Canvas capture failed: ' + e.message });
      }
    }

    function createPC() {
      if (pc) return;
      pc = new RTCPeerConnection({ iceServers: iceOptions });
      videoEl = document.createElement('video');
      videoEl.autoplay = true;
      videoEl.playsInline = true;
      videoEl.muted = true;

      pc.ontrack = function (ev) {
        setStatus('Video track received, waiting for frame...');
        videoEl.srcObject = ev.streams[0] || new MediaStream([ev.track]);
        videoEl.onloadeddata = function () {
          setStatus('Frame ready, capturing...');
          setTimeout(captureFrame, 200);
        };
      };

      pc.onicecandidate = function (ev) {
        if (ev.candidate && ws && ws.readyState === 1) {
          ws.send(JSON.stringify({ type: 'iceCandidate', candidate: ev.candidate }));
        }
      };
    }

    function handleOffer(msg) {
      createPC();
      var sdpStr = msg.sdp || msg;
      if (typeof sdpStr === 'object') sdpStr = sdpStr.sdp;
      var desc = new RTCSessionDescription({ type: 'offer', sdp: sdpStr });

      setStatus('Processing offer, creating answer...');
      pc.setRemoteDescription(desc)
        .then(function () { return pc.createAnswer(); })
        .then(function (answer) {
          return pc.setLocalDescription(answer).then(function () { return answer; });
        })
        .then(function (answer) {
          if (ws && ws.readyState === 1) {
            ws.send(JSON.stringify({ type: 'answer', sdp: answer.sdp }));
          }
          setStatus('Answer sent, waiting for video track...');
        })
        .catch(function (e) {
          finish({ error: 'WebRTC error: ' + e.message });
        });
    }

    try { ws = new WebSocket(wsUrl); }
    catch (e) { finish({ error: 'WebSocket error: ' + e.message }); return; }

    setStatus('Connecting to ' + wsUrl + '...');

    ws.onopen = function () {
      setStatus('Connected. Waiting for config from server...');
    };

    ws.onmessage = function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      var t = msg.type;

      if (t === 'config') {
        configReceived = true;
        iceOptions = (msg.peerConnectionOptions && msg.peerConnectionOptions.iceServers)
          ? msg.peerConnectionOptions.iceServers : [];
        setStatus('Config received. Requesting streamer list...');
        ws.send(JSON.stringify({ type: 'listStreamers' }));

        fallbackTimer = setTimeout(function () {
          if (!done && !pc) {
            setStatus('No streamerList received. Trying default subscribe...');
            ws.send(JSON.stringify({ type: 'subscribe', streamerId: 'DefaultStreamer' }));
          }
        }, 3000);

      } else if (t === 'playerCount') {
        /* ignore */

      } else if (t === 'streamerList') {
        clearTimeout(fallbackTimer);
        var ids = msg.ids || msg.streamerList || [];
        var sid = (ids.length > 0) ? ids[0] : 'DefaultStreamer';
        setStatus('Subscribing to streamer: ' + sid + '...');
        ws.send(JSON.stringify({ type: 'subscribe', streamerId: sid }));

      } else if (t === 'offer') {
        clearTimeout(fallbackTimer);
        setStatus('Offer received. Setting up WebRTC...');
        handleOffer(msg);

      } else if (t === 'iceCandidate') {
        if (pc && msg.candidate) {
          try {
            var ic = typeof msg.candidate === 'string'
              ? JSON.parse(msg.candidate) : msg.candidate;
            pc.addIceCandidate(new RTCIceCandidate(ic));
          } catch (e) {}
        }

      } else if (t === 'ping') {
        ws.send(JSON.stringify({ type: 'pong', time: msg.time }));

      } else if (t === 'streamerDisconnected' || t === 'error') {
        finish({ error: 'Server: ' + (msg.reason || msg.error || t) });

      } else {
        /* unknown message – log but keep going */
      }
    };

    ws.onerror = function () {
      finish({ error: 'Cannot reach signalling server at ' + wsUrl });
    };

    ws.onclose = function (ev) {
      if (!done) {
        finish({
          error: 'Server closed connection (code ' + ev.code + '). ' +
                 (configReceived ? 'Config was received.' : 'No config received – wrong URL?')
        });
      }
    };

    timeout = setTimeout(function () {
      var state = configReceived ? 'Config received but no video.' : 'No config from server.';
      finish({ error: 'Timeout (12s). ' + state });
    }, 12000);
  }

  /* ── Screenshot (disconnect iframe → capture → reconnect) ── */
  function takeScreenshot() {
    if (!currentUrl) { setStatus('Load a stream first.'); return; }

    setStatus('Disconnecting iframe to free signalling slot...');
    btnAction.style.opacity = '0.5';
    btnAction.disabled = true;

    vpFrame.src = 'about:blank';

    setTimeout(function () {
      doWebRTCCapture(function (result) {
        setStatus('Restoring live stream...');
        vpFrame.src = currentUrl;
        btnAction.style.opacity = '1';
        btnAction.disabled = false;

        if (result && result.dataUrl) {
          flash();
          var kb = Math.round(result.dataUrl.length * 3 / 4 / 1024);
          setStatus('Captured ' + result.width + ' x ' + result.height +
            ' (' + kb + ' KB) – run flow for output');
          showThumb(result.dataUrl, result.width, result.height);
          if (onChange) onChange({ url: currentUrl, screenshot: result.dataUrl });
        } else {
          setStatus('FAILED: ' + (result ? result.error : 'unknown error'));
        }
      });
    }, 1500);
  }

  /* ── Events ── */
  function stop(e) { e.stopPropagation(); }

  btnAction.addEventListener('click', function (e) {
    e.stopPropagation(); e.preventDefault();
    if (streamLoaded && !e.shiftKey) takeScreenshot();
    else loadUrl();
  });

  urlInp.addEventListener('keydown', function (e) {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); loadUrl(); }
  });
  urlInp.addEventListener('keyup',  stop);
  urlInp.addEventListener('input',  stop);
  widget.addEventListener('pointerdown', stop);
  widget.addEventListener('mousedown',   stop);

  return function () { if (vpFrame) vpFrame.src = ''; };
}
