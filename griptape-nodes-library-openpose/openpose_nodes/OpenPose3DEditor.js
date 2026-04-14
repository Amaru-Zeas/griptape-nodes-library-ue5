/**
 * OpenPose3DEditor – Full-featured 3D OpenPose skeleton editor widget for Griptape Nodes.
 *
 * Features ported from sd-webui-3d-open-pose-editor:
 *   • 18-keypoint OpenPose skeleton with correct colors
 *   • Joint rotation via TransformControls (rotate / translate modes)
 *   • Camera orbit, zoom, pan via OrbitControls
 *   • Body parameter adjustment (shoulder width, arm/leg length, torso, etc.)
 *   • Preset poses (T-pose, A-pose, Walking, Sitting, Relaxed)
 *   • Capture pose image (skeleton on black background)
 *   • Depth map & Normal map generation
 *   • Save / Load scene as JSON
 *   • Undo / Redo (Ctrl+Z / Ctrl+Y)
 *   • Keyboard shortcuts: X = translate mode, R = rotate mode
 *
 * Uses THREE.js r128 loaded from CDN.
 */

export default function OpenPose3DEditor(container, props) {
  const { value, onChange, disabled, height } = props;

  // ═══════════════════════════════════════════════════════════════════
  // CONSTANTS
  // ═══════════════════════════════════════════════════════════════════
  const KEYPOINT_NAMES = [
    'nose','neck','right_shoulder','right_elbow','right_wrist',
    'left_shoulder','left_elbow','left_wrist','right_hip','right_knee',
    'right_ankle','left_hip','left_knee','left_ankle','right_eye',
    'left_eye','right_ear','left_ear'
  ];

  const CONNECTIONS = [
    [1,2],[1,5],[2,3],[3,4],[5,6],[6,7],[1,8],[8,9],[9,10],
    [1,11],[11,12],[12,13],[0,1],[0,14],[14,16],[0,15],[15,17]
  ];

  const CONNECT_COLORS = [
    [255,0,0],[255,85,0],[255,170,0],[255,255,0],[170,255,0],
    [85,255,0],[0,255,0],[0,255,85],[0,255,170],[0,255,255],
    [0,170,255],[0,85,255],[0,0,255],[85,0,255],[170,0,255],
    [255,0,255],[255,0,170],[255,0,85]
  ];

  function rgbToHex(r, g, b) { return (r << 16) | (g << 8) | b; }

  const JOINT_COLORS = {};
  KEYPOINT_NAMES.forEach((name, i) => {
    const c = CONNECT_COLORS[i] || [255, 0, 0];
    JOINT_COLORS[name] = rgbToHex(c[0], c[1], c[2]);
  });

  function getLinkColor(startIdx, endIdx) {
    const ci = CONNECTIONS.findIndex(([s, e]) => (s === startIdx && e === endIdx) || (s === endIdx && e === startIdx));
    if (ci >= 0) { const c = CONNECT_COLORS[ci]; return rgbToHex(c[0], c[1], c[2]); }
    return 0x888888;
  }

  const BONE_RADIUS = 1.5;
  const viewportH = height && height > 0 ? Math.max(300, height - 160) : 420;

  // ═══════════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════════
  let scene, camera, renderer, orbitControls, transformControl;
  let bodyRoot = null;
  let jointMap = {};   // name → THREE.Group
  let linkMeshes = []; // array of { mesh, startName, endName }
  let selectedJoint = null;
  let animId = null;
  let undoStack = [];
  let redoStack = [];
  let currentMode = 'rotate';
  let gridHelper, axesHelper;

  // ═══════════════════════════════════════════════════════════════════
  // DOM
  // ═══════════════════════════════════════════════════════════════════
  container.innerHTML = `
  <div class="op3d-root nodrag nowheel" style="
    display:flex;flex-direction:column;gap:4px;padding:6px;
    background:#111;border-radius:6px;user-select:none;width:100%;box-sizing:border-box;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:11px;color:#ccc;">

    <!-- Toolbar -->
    <div class="op3d-toolbar" style="display:flex;flex-wrap:wrap;gap:3px;align-items:center;">
      <span style="color:#888;font-size:10px;margin-right:4px;">Pose:</span>
      <button class="op3d-btn" data-preset="tpose">T-Pose</button>
      <button class="op3d-btn" data-preset="apose">A-Pose</button>
      <button class="op3d-btn" data-preset="walking">Walk</button>
      <button class="op3d-btn" data-preset="sitting">Sit</button>
      <button class="op3d-btn" data-preset="relaxed">Relax</button>
      <span style="color:#444;margin:0 2px;">|</span>
      <button class="op3d-btn op3d-cap" data-cap="pose" title="Capture skeleton image">📷 Pose</button>
      <button class="op3d-btn op3d-cap" data-cap="depth" title="Capture depth map">📷 Depth</button>
      <button class="op3d-btn op3d-cap" data-cap="normal" title="Capture normal map">📷 Normal</button>
      <span style="color:#444;margin:0 2px;">|</span>
      <button class="op3d-btn" data-action="save" title="Save scene to JSON">💾 Save</button>
      <button class="op3d-btn" data-action="load" title="Load scene from JSON">📂 Load</button>
      <button class="op3d-btn" data-action="undo" title="Undo (Ctrl+Z)">↩</button>
      <button class="op3d-btn" data-action="redo" title="Redo (Ctrl+Y)">↪</button>
    </div>

    <!-- 3D Viewport -->
    <div class="op3d-viewport" style="
      width:100%;height:${viewportH}px;position:relative;
      border-radius:4px;overflow:hidden;background:#1a1a1a;">
      <div class="op3d-info" style="
        position:absolute;top:6px;left:8px;font-size:10px;color:#888;z-index:5;pointer-events:none;">
        <div class="op3d-selected" style="color:#eee;">No joint selected</div>
        <div style="margin-top:2px;">Mode: <span class="op3d-mode" style="color:#0f0;">Rotate</span></div>
        <div style="margin-top:1px;color:#555;">Click joint → rotate | X = move | Scroll = zoom</div>
      </div>
    </div>

    <!-- Mode toggle -->
    <div style="display:flex;gap:4px;align-items:center;">
      <span style="color:#888;font-size:10px;">Mode:</span>
      <button class="op3d-btn op3d-mode-btn" data-mode="rotate" style="background:#1a3a1a;border-color:#2a5a2a;">Rotate (R)</button>
      <button class="op3d-btn op3d-mode-btn" data-mode="translate">Translate (X)</button>
      <span style="flex:1;"></span>
      <label style="font-size:10px;color:#888;display:flex;align-items:center;gap:4px;">
        <input type="checkbox" class="op3d-grid-toggle" checked style="margin:0;"> Grid
      </label>
    </div>

    <!-- Body Parameters (collapsible) -->
    <details class="op3d-params" style="background:#1a1a1a;border-radius:4px;padding:4px 8px;">
      <summary style="cursor:pointer;color:#aaa;font-size:10px;font-weight:600;">▸ Body Parameters</summary>
      <div class="op3d-sliders" style="display:grid;grid-template-columns:auto 1fr auto;gap:3px 8px;margin-top:6px;align-items:center;font-size:10px;">
      </div>
    </details>

    <!-- Hidden file input for load -->
    <input type="file" class="op3d-file-input" accept=".json" style="display:none;" />
  </div>`;

  // Inject button styles
  const style = document.createElement('style');
  style.textContent = `
    .op3d-btn { padding:3px 7px; font-size:10px; background:#252525; border:1px solid #444;
      border-radius:3px; color:#ddd; cursor:pointer; white-space:nowrap; }
    .op3d-btn:hover { background:#333; border-color:#666; }
    .op3d-btn:active { background:#444; }
    .op3d-cap { background:#1a2a3a; border-color:#2a4a5a; }
    .op3d-cap:hover { background:#2a3a5a; }
  `;
  container.appendChild(style);

  // Grab DOM refs
  const rootEl = container.querySelector('.op3d-root');
  const viewport = container.querySelector('.op3d-viewport');
  const infoSelected = container.querySelector('.op3d-selected');
  const infoMode = container.querySelector('.op3d-mode');
  const slidersDiv = container.querySelector('.op3d-sliders');
  const fileInput = container.querySelector('.op3d-file-input');

  // ═══════════════════════════════════════════════════════════════════
  // THREE.JS LOADING
  // ═══════════════════════════════════════════════════════════════════
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector('script[src="' + src + '"]')) {
        const check = setInterval(() => {
          if (window.THREE) { clearInterval(check); resolve(); }
        }, 50);
        setTimeout(() => { clearInterval(check); resolve(); }, 3000);
        return;
      }
      const s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  let threeLoaded = false;
  async function loadThree() {
    if (threeLoaded && window.THREE && window.THREE.OrbitControls) return window.THREE;
    await loadScript('https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js');
    // Wait for THREE to be available
    await new Promise(r => { const iv = setInterval(() => { if (window.THREE) { clearInterval(iv); r(); } }, 30); });
    await loadScript('https://unpkg.com/three@0.128.0/examples/js/controls/OrbitControls.js');
    await loadScript('https://unpkg.com/three@0.128.0/examples/js/controls/TransformControls.js');
    threeLoaded = true;
    return window.THREE;
  }

  // ═══════════════════════════════════════════════════════════════════
  // BODY MODEL
  // ═══════════════════════════════════════════════════════════════════
  function createJoint(THREE, name, x, y, z) {
    const g = new THREE.Group();
    g.name = name;
    g.position.set(x, y, z);
    g.userData.isJoint = true;
    g.userData.jointName = name;

    const color = JOINT_COLORS[name] || 0xff0000;
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(BONE_RADIUS, 12, 12),
      new THREE.MeshBasicMaterial({ color: color })
    );
    sphere.name = name + '_vis';
    sphere.userData.jointName = name;
    g.add(sphere);
    return g;
  }

  function createLink(THREE, startName, endName, startObj, endObj) {
    const si = KEYPOINT_NAMES.indexOf(startName);
    const ei = KEYPOINT_NAMES.indexOf(endName);
    const color = getLinkColor(si, ei);

    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(1, 8, 6),
      new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.85 })
    );
    mesh.name = startName + '_link_' + endName;
    startObj.add(mesh);
    return { mesh, startName, endName, startObj, endObj };
  }

  function updateLink(THREE, link) {
    const start = new THREE.Vector3(0, 0, 0);
    const end = link.endObj.position;
    const dist = start.distanceTo(end);
    if (dist < 0.01) return;

    const mid = start.clone().add(end).multiplyScalar(0.5);
    const dir = end.clone().sub(start);
    const unit = new THREE.Vector3(1, 0, 0);
    const axis = unit.clone().cross(dir);
    const angle = unit.angleTo(dir);

    link.mesh.position.copy(mid);
    link.mesh.scale.set(dist / 2, BONE_RADIUS / 1, BONE_RADIUS / 1);
    if (axis.length() > 0.001) {
      link.mesh.setRotationFromAxisAngle(axis.normalize(), angle);
    }
  }

  /**
   * Build the hierarchical skeleton.
   * Positions create a T-pose (arms out, legs straight down).
   */
  function buildBody(THREE) {
    const j = (n, x, y, z) => createJoint(THREE, n, x, y, z);

    // Root = torso (pelvis area)
    const torso = new THREE.Group();
    torso.name = 'torso';
    torso.position.set(0, 95, 0);
    torso.userData.isRoot = true;

    // Spine center (shoulder level)
    const spine = new THREE.Group();
    spine.name = 'spine';
    spine.position.set(0, 45, 0);
    torso.add(spine);

    // Neck
    const neck = j('neck', 0, 0, 0);
    spine.add(neck);

    // Head
    const nose = j('nose', 0, 15, 10);
    neck.add(nose);
    const rEye = j('right_eye', -4, 4, 0);
    nose.add(rEye);
    const rEar = j('right_ear', -3, -2, -5);
    rEye.add(rEar);
    const lEye = j('left_eye', 4, 4, 0);
    nose.add(lEye);
    const lEar = j('left_ear', 3, -2, -5);
    lEye.add(lEar);

    // Right arm (T-pose: extends to negative X)
    const rShoulder = j('right_shoulder', -18, 0, 0);
    spine.add(rShoulder);
    const rElbow = j('right_elbow', -24, 0, 0);
    rShoulder.add(rElbow);
    const rWrist = j('right_wrist', -24, 0, 0);
    rElbow.add(rWrist);

    // Left arm (T-pose: extends to positive X)
    const lShoulder = j('left_shoulder', 18, 0, 0);
    spine.add(lShoulder);
    const lElbow = j('left_elbow', 24, 0, 0);
    lShoulder.add(lElbow);
    const lWrist = j('left_wrist', 24, 0, 0);
    lElbow.add(lWrist);

    // Right leg
    const rHip = j('right_hip', -10, -45, 0);
    spine.add(rHip);
    const rKnee = j('right_knee', 0, -40, 0);
    rHip.add(rKnee);
    const rAnkle = j('right_ankle', 0, -36, 0);
    rKnee.add(rAnkle);

    // Left leg
    const lHip = j('left_hip', 10, -45, 0);
    spine.add(lHip);
    const lKnee = j('left_knee', 0, -40, 0);
    lHip.add(lKnee);
    const lAnkle = j('left_ankle', 0, -36, 0);
    lKnee.add(lAnkle);

    // Build joint map
    jointMap = {};
    torso.traverse(o => {
      if (o.userData.isJoint) jointMap[o.name] = o;
    });

    // Build links
    linkMeshes = [];
    const linkDefs = [
      ['neck', 'nose'],
      ['nose', 'right_eye'], ['right_eye', 'right_ear'],
      ['nose', 'left_eye'], ['left_eye', 'left_ear'],
      ['neck', 'right_shoulder'], ['right_shoulder', 'right_elbow'], ['right_elbow', 'right_wrist'],
      ['neck', 'left_shoulder'], ['left_shoulder', 'left_elbow'], ['left_elbow', 'left_wrist'],
      ['neck', 'right_hip'], ['right_hip', 'right_knee'], ['right_knee', 'right_ankle'],
      ['neck', 'left_hip'], ['left_hip', 'left_knee'], ['left_knee', 'left_ankle'],
    ];

    linkDefs.forEach(([sn, en]) => {
      // Find parent→child for the link
      // The link goes from sn (parent joint) to en (child joint)
      // We need to determine which one is the parent in the hierarchy
      const sObj = jointMap[sn];
      const eObj = jointMap[en];
      if (!sObj || !eObj) return;

      // Check if eObj is a direct or indirect child of sObj
      let parentObj = sObj;
      let childObj = eObj;

      // If eObj's parent chain includes sObj, then sObj→eObj is correct
      let found = false;
      let cur = eObj.parent;
      while (cur) {
        if (cur === sObj) { found = true; break; }
        if (cur === sObj.parent && cur.name === 'spine') {
          // They're siblings under spine
          // For links between siblings (neck→shoulder, neck→hip), we handle differently
          break;
        }
        cur = cur.parent;
      }

      if (found) {
        // Direct parent→child link: create as child of parent, pointing to child
        linkMeshes.push(createLink(THREE, sn, en, sObj, eObj));
      } else {
        // Siblings: neck→shoulder, neck→hip
        // These are both children of spine. Create a world-space link instead.
        // We'll create a link mesh in the scene and update it with world positions each frame.
        const si = KEYPOINT_NAMES.indexOf(sn);
        const ei = KEYPOINT_NAMES.indexOf(en);
        const color = getLinkColor(si, ei);
        const mesh = new THREE.Mesh(
          new THREE.SphereGeometry(1, 8, 6),
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85 })
        );
        mesh.name = sn + '_wlink_' + en;
        scene.add(mesh);
        linkMeshes.push({ mesh, startName: sn, endName: en, startObj: sObj, endObj: eObj, worldSpace: true });
      }
    });

    return torso;
  }

  function updateAllLinks(THREE) {
    linkMeshes.forEach(link => {
      if (link.worldSpace) {
        // World-space link between siblings
        const sp = new THREE.Vector3();
        const ep = new THREE.Vector3();
        link.startObj.getWorldPosition(sp);
        link.endObj.getWorldPosition(ep);
        const dist = sp.distanceTo(ep);
        if (dist < 0.01) return;
        const mid = sp.clone().add(ep).multiplyScalar(0.5);
        const dir = ep.clone().sub(sp);
        const unit = new THREE.Vector3(1, 0, 0);
        const axis = unit.clone().cross(dir);
        const angle = unit.angleTo(dir);
        link.mesh.position.copy(mid);
        link.mesh.scale.set(dist / 2, BONE_RADIUS, BONE_RADIUS);
        if (axis.length() > 0.001) link.mesh.setRotationFromAxisAngle(axis.normalize(), angle);
      } else {
        updateLink(THREE, link);
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // SCENE DATA (Save / Load / Undo)
  // ═══════════════════════════════════════════════════════════════════
  function getJointData() {
    const data = {};
    const THREE = window.THREE;
    Object.entries(jointMap).forEach(([name, obj]) => {
      const wp = new THREE.Vector3();
      obj.getWorldPosition(wp);
      data[name] = [Math.round(wp.x * 100) / 100, Math.round(wp.y * 100) / 100, Math.round(wp.z * 100) / 100];
    });
    return data;
  }

  function getSceneState() {
    const state = { joints: {} };
    Object.entries(jointMap).forEach(([name, obj]) => {
      state.joints[name] = {
        position: obj.position.toArray(),
        rotation: [obj.rotation.x, obj.rotation.y, obj.rotation.z],
        scale: obj.scale.toArray(),
      };
    });
    if (bodyRoot) {
      state.torso = {
        position: bodyRoot.position.toArray(),
        rotation: [bodyRoot.rotation.x, bodyRoot.rotation.y, bodyRoot.rotation.z],
      };
    }
    if (camera) {
      state.camera = {
        position: camera.position.toArray(),
        target: orbitControls ? orbitControls.target.toArray() : [0, 100, 0],
      };
    }
    return state;
  }

  function restoreSceneState(state) {
    if (!state || !state.joints) return;
    Object.entries(state.joints).forEach(([name, data]) => {
      const obj = jointMap[name];
      if (!obj) return;
      if (data.position) obj.position.fromArray(data.position);
      if (data.rotation) obj.rotation.set(data.rotation[0], data.rotation[1], data.rotation[2]);
      if (data.scale) obj.scale.fromArray(data.scale);
    });
    if (state.torso && bodyRoot) {
      bodyRoot.position.fromArray(state.torso.position);
      if (state.torso.rotation) bodyRoot.rotation.set(state.torso.rotation[0], state.torso.rotation[1], state.torso.rotation[2]);
    }
    if (state.camera && camera && orbitControls) {
      camera.position.fromArray(state.camera.position);
      orbitControls.target.fromArray(state.camera.target);
      orbitControls.update();
    }
  }

  function pushUndo() {
    undoStack.push(JSON.stringify(getSceneState()));
    if (undoStack.length > 50) undoStack.shift();
    redoStack = [];
  }

  function doUndo() {
    if (undoStack.length === 0) return;
    redoStack.push(JSON.stringify(getSceneState()));
    const prev = JSON.parse(undoStack.pop());
    restoreSceneState(prev);
  }

  function doRedo() {
    if (redoStack.length === 0) return;
    undoStack.push(JSON.stringify(getSceneState()));
    const next = JSON.parse(redoStack.pop());
    restoreSceneState(next);
  }

  // ═══════════════════════════════════════════════════════════════════
  // CAPTURE / MAP FUNCTIONS
  // ═══════════════════════════════════════════════════════════════════
  function capturePoseImage() {
    const THREE = window.THREE;
    if (!renderer || !scene || !camera) return null;

    // Save state
    const oldBg = renderer.getClearColor(new THREE.Color());
    const oldAlpha = renderer.getClearAlpha();
    const tcVis = transformControl ? transformControl.visible : false;
    const gridVis = gridHelper ? gridHelper.visible : false;
    const axesVis = axesHelper ? axesHelper.visible : false;

    // Hide helpers
    if (transformControl) transformControl.visible = false;
    if (gridHelper) gridHelper.visible = false;
    if (axesHelper) axesHelper.visible = false;

    renderer.setClearColor(0x000000, 1.0);
    renderer.render(scene, camera);
    const dataUrl = renderer.domElement.toDataURL('image/png');

    // Restore
    renderer.setClearColor(oldBg, oldAlpha);
    if (transformControl) transformControl.visible = tcVis;
    if (gridHelper) gridHelper.visible = gridVis;
    if (axesHelper) axesHelper.visible = axesVis;

    return dataUrl;
  }

  function captureDepthMap() {
    const THREE = window.THREE;
    if (!renderer || !scene || !camera) return null;

    const origMaterials = new Map();
    const depthMat = new THREE.MeshDepthMaterial();

    // Save and override materials
    scene.traverse(o => {
      if (o.isMesh && o.material) {
        origMaterials.set(o, o.material);
        o.material = depthMat;
      }
    });

    // Adjust camera near/far for depth range
    const oldNear = camera.near;
    const oldFar = camera.far;
    camera.near = 50;
    camera.far = 400;
    camera.updateProjectionMatrix();

    const oldBg = renderer.getClearColor(new THREE.Color());
    const oldAlpha = renderer.getClearAlpha();
    const tcVis = transformControl ? transformControl.visible : false;
    const gridVis = gridHelper ? gridHelper.visible : false;
    const axesVis = axesHelper ? axesHelper.visible : false;

    if (transformControl) transformControl.visible = false;
    if (gridHelper) gridHelper.visible = false;
    if (axesHelper) axesHelper.visible = false;

    renderer.setClearColor(0x000000, 1.0);
    renderer.render(scene, camera);
    const dataUrl = renderer.domElement.toDataURL('image/png');

    // Restore everything
    origMaterials.forEach((mat, obj) => { obj.material = mat; });
    camera.near = oldNear;
    camera.far = oldFar;
    camera.updateProjectionMatrix();
    renderer.setClearColor(oldBg, oldAlpha);
    if (transformControl) transformControl.visible = tcVis;
    if (gridHelper) gridHelper.visible = gridVis;
    if (axesHelper) axesHelper.visible = axesVis;

    return dataUrl;
  }

  function captureNormalMap() {
    const THREE = window.THREE;
    if (!renderer || !scene || !camera) return null;

    const origMaterials = new Map();
    const normalMat = new THREE.MeshNormalMaterial();

    scene.traverse(o => {
      if (o.isMesh && o.material) {
        origMaterials.set(o, o.material);
        o.material = normalMat;
      }
    });

    const oldBg = renderer.getClearColor(new THREE.Color());
    const oldAlpha = renderer.getClearAlpha();
    const tcVis = transformControl ? transformControl.visible : false;
    const gridVis = gridHelper ? gridHelper.visible : false;
    const axesVis = axesHelper ? axesHelper.visible : false;

    if (transformControl) transformControl.visible = false;
    if (gridHelper) gridHelper.visible = false;
    if (axesHelper) axesHelper.visible = false;

    renderer.setClearColor(0x000000, 1.0);
    renderer.render(scene, camera);
    const dataUrl = renderer.domElement.toDataURL('image/png');

    origMaterials.forEach((mat, obj) => { obj.material = mat; });
    renderer.setClearColor(oldBg, oldAlpha);
    if (transformControl) transformControl.visible = tcVis;
    if (gridHelper) gridHelper.visible = gridVis;
    if (axesHelper) axesHelper.visible = axesVis;

    return dataUrl;
  }

  // ═══════════════════════════════════════════════════════════════════
  // PRESET POSES
  // ═══════════════════════════════════════════════════════════════════
  // Each preset defines LOCAL rotations for joints (radians).
  // Positions remain at their defaults (T-pose geometry).
  const PI = Math.PI;
  const PRESETS = {
    tpose: {},
    apose: {
      right_shoulder: { rz: 0.4 },    // arms angled down ~23°
      left_shoulder:  { rz: -0.4 },
    },
    walking: {
      right_shoulder: { rx: -0.35, rz: 0.15 },
      left_shoulder:  { rx: 0.35, rz: -0.15 },
      right_elbow:    { rz: 0.3 },
      left_elbow:     { rz: -0.3 },
      right_hip:      { rx: 0.4 },
      left_hip:       { rx: -0.25 },
      right_knee:     { rx: -0.2 },
      left_knee:      { rx: 0.5 },
    },
    sitting: {
      right_hip:    { rx: -PI/2 },
      left_hip:     { rx: -PI/2 },
      right_knee:   { rx: PI/2 },
      left_knee:    { rx: PI/2 },
      right_shoulder: { rz: 0.3 },
      left_shoulder:  { rz: -0.3 },
      right_elbow:  { rx: -PI/4, rz: 0.4 },
      left_elbow:   { rx: -PI/4, rz: -0.4 },
    },
    relaxed: {
      right_shoulder: { rz: 0.25, rx: 0.1 },
      left_shoulder:  { rz: -0.25, rx: 0.1 },
      right_elbow:    { rz: 0.35, ry: -0.2 },
      left_elbow:     { rz: -0.35, ry: 0.2 },
      right_hip:      { rx: 0.05 },
      left_hip:       { rx: -0.05 },
      nose:           { rx: 0.1 },
    },
  };

  function applyPreset(name) {
    pushUndo();
    const preset = PRESETS[name] || {};

    // Reset all rotations to zero first
    Object.values(jointMap).forEach(obj => {
      obj.rotation.set(0, 0, 0);
    });
    if (bodyRoot) {
      bodyRoot.rotation.set(0, 0, 0);
      bodyRoot.position.set(0, 95, 0);
    }

    // Apply preset rotations
    Object.entries(preset).forEach(([jname, rots]) => {
      const obj = jointMap[jname];
      if (!obj) return;
      obj.rotation.set(rots.rx || 0, rots.ry || 0, rots.rz || 0);
    });

    emitChange();
  }

  // ═══════════════════════════════════════════════════════════════════
  // BODY PARAMETERS
  // ═══════════════════════════════════════════════════════════════════
  const bodyParams = [
    { name: 'shoulder_width', label: 'Shoulders', min: 10, max: 40, get: () => Math.abs(jointMap['right_shoulder']?.position.x || 18),
      set: v => { if (jointMap['right_shoulder']) jointMap['right_shoulder'].position.x = -v;
                   if (jointMap['left_shoulder']) jointMap['left_shoulder'].position.x = v; }},
    { name: 'upper_arm', label: 'Upper Arm', min: 10, max: 40, get: () => Math.abs(jointMap['right_elbow']?.position.x || 24),
      set: v => { if (jointMap['right_elbow']) jointMap['right_elbow'].position.x = -v;
                   if (jointMap['left_elbow']) jointMap['left_elbow'].position.x = v; }},
    { name: 'forearm', label: 'Forearm', min: 10, max: 40, get: () => Math.abs(jointMap['right_wrist']?.position.x || 24),
      set: v => { if (jointMap['right_wrist']) jointMap['right_wrist'].position.x = -v;
                   if (jointMap['left_wrist']) jointMap['left_wrist'].position.x = v; }},
    { name: 'torso_height', label: 'Torso', min: 20, max: 70, get: () => {
        const s = bodyRoot?.children.find(c => c.name === 'spine');
        return s ? s.position.y : 45; },
      set: v => { const s = bodyRoot?.children.find(c => c.name === 'spine');
                   if (s) s.position.y = v; }},
    { name: 'hip_width', label: 'Hips', min: 5, max: 25, get: () => Math.abs(jointMap['right_hip']?.position.x || 10),
      set: v => { if (jointMap['right_hip']) jointMap['right_hip'].position.x = -v;
                   if (jointMap['left_hip']) jointMap['left_hip'].position.x = v; }},
    { name: 'thigh', label: 'Thigh', min: 20, max: 60, get: () => Math.abs(jointMap['right_knee']?.position.y || 40),
      set: v => { if (jointMap['right_knee']) jointMap['right_knee'].position.y = -v;
                   if (jointMap['left_knee']) jointMap['left_knee'].position.y = -v; }},
    { name: 'lower_leg', label: 'Lower Leg', min: 20, max: 55, get: () => Math.abs(jointMap['right_ankle']?.position.y || 36),
      set: v => { if (jointMap['right_ankle']) jointMap['right_ankle'].position.y = -v;
                   if (jointMap['left_ankle']) jointMap['left_ankle'].position.y = -v; }},
  ];

  function buildParamSliders() {
    slidersDiv.innerHTML = '';
    bodyParams.forEach(p => {
      const val = Math.round(p.get());
      slidersDiv.innerHTML += `
        <span style="color:#aaa;">${p.label}</span>
        <input type="range" class="op3d-slider" data-param="${p.name}" min="${p.min}" max="${p.max}" value="${val}"
          style="width:100%;height:14px;accent-color:#4a9;cursor:pointer;" />
        <span class="op3d-val" data-param="${p.name}" style="color:#eee;min-width:24px;text-align:right;">${val}</span>
      `;
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // EMIT CHANGE TO PYTHON NODE
  // ═══════════════════════════════════════════════════════════════════
  function emitChange(extra) {
    if (disabled || !onChange) return;
    const out = {
      joints: getJointData(),
      captured_image: null,
      depth_map: null,
      normal_map: null,
      scene_json: JSON.stringify(getSceneState()),
    };
    if (extra) Object.assign(out, extra);
    onChange(out);
  }

  // ═══════════════════════════════════════════════════════════════════
  // SELECTION & MODE
  // ═══════════════════════════════════════════════════════════════════
  function selectJoint(name) {
    selectedJoint = name;
    const obj = jointMap[name];
    if (obj && transformControl) {
      transformControl.attach(obj);
      transformControl.setMode(currentMode);
      if (currentMode === 'translate') {
        transformControl.setSpace('world');
      } else {
        transformControl.setSpace('local');
      }
    }
    infoSelected.textContent = name ? ('Selected: ' + name) : 'No joint selected';

    // Highlight selected joint
    Object.entries(jointMap).forEach(([n, o]) => {
      const vis = o.children.find(c => c.name === n + '_vis');
      if (vis && vis.material) {
        if (n === name) {
          vis.material.color.set(0xffff00);
          vis.scale.setScalar(1.4);
        } else {
          vis.material.color.set(JOINT_COLORS[n] || 0xff0000);
          vis.scale.setScalar(1.0);
        }
      }
    });
  }

  function deselectJoint() {
    selectedJoint = null;
    if (transformControl) transformControl.detach();
    infoSelected.textContent = 'No joint selected';
    Object.entries(jointMap).forEach(([n, o]) => {
      const vis = o.children.find(c => c.name === n + '_vis');
      if (vis && vis.material) {
        vis.material.color.set(JOINT_COLORS[n] || 0xff0000);
        vis.scale.setScalar(1.0);
      }
    });
  }

  function setMode(mode) {
    currentMode = mode;
    infoMode.textContent = mode.charAt(0).toUpperCase() + mode.slice(1);
    infoMode.style.color = mode === 'rotate' ? '#0f0' : '#fa0';

    // Update mode buttons
    rootEl.querySelectorAll('.op3d-mode-btn').forEach(btn => {
      if (btn.dataset.mode === mode) {
        btn.style.background = '#1a3a1a';
        btn.style.borderColor = '#2a5a2a';
      } else {
        btn.style.background = '#252525';
        btn.style.borderColor = '#444';
      }
    });

    if (transformControl && selectedJoint) {
      transformControl.setMode(mode);
      transformControl.setSpace(mode === 'translate' ? 'world' : 'local');
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  // MAIN INIT
  // ═══════════════════════════════════════════════════════════════════
  async function initScene() {
    const THREE = await loadThree();

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(viewport.clientWidth, viewport.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x1a1a1a, 1.0);
    viewport.insertBefore(renderer.domElement, viewport.firstChild);

    // Scene
    scene = new THREE.Scene();

    // Camera
    camera = new THREE.PerspectiveCamera(50, viewport.clientWidth / viewport.clientHeight, 0.1, 5000);
    camera.position.set(0, 120, 280);
    camera.lookAt(0, 100, 0);

    // Lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dlight = new THREE.DirectionalLight(0xffffff, 0.8);
    dlight.position.set(100, 200, 300);
    scene.add(dlight);

    // Grid & Axes
    gridHelper = new THREE.GridHelper(400, 40, 0x333333, 0x222222);
    scene.add(gridHelper);
    axesHelper = new THREE.AxesHelper(50);
    scene.add(axesHelper);

    // OrbitControls
    orbitControls = new THREE.OrbitControls(camera, renderer.domElement);
    orbitControls.target.set(0, 100, 0);
    orbitControls.update();
    orbitControls.enableDamping = true;
    orbitControls.dampingFactor = 0.08;

    // TransformControls
    transformControl = new THREE.TransformControls(camera, renderer.domElement);
    transformControl.setMode('rotate');
    transformControl.setSize(0.6);
    transformControl.setSpace('local');
    scene.add(transformControl);

    // Disable orbit when using transform
    transformControl.addEventListener('dragging-changed', (e) => {
      orbitControls.enabled = !e.value;
      if (!e.value) {
        // Drag ended → emit change
        emitChange();
      }
    });

    // Push undo before transform starts
    transformControl.addEventListener('mouseDown', () => {
      pushUndo();
    });

    // Build body
    bodyRoot = buildBody(THREE);
    scene.add(bodyRoot);

    // Initial link update
    bodyRoot.updateMatrixWorld(true);
    updateAllLinks(THREE);

    // Restore from value if provided
    if (value && typeof value === 'object' && value.scene_json) {
      try {
        restoreSceneState(JSON.parse(value.scene_json));
      } catch (e) { console.warn('Failed to restore scene:', e); }
    }

    // Build body param sliders
    buildParamSliders();

    // Raycasting for joint selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let isClick = true;

    function onPointerDown(e) {
      isClick = true;
    }
    function onPointerMove(e) {
      if (Math.abs(e.movementX) > 1 || Math.abs(e.movementY) > 1) isClick = false;
    }
    function onPointerUp(e) {
      if (!isClick) return;
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);

      // Collect all joint spheres
      const meshes = [];
      Object.values(jointMap).forEach(j => {
        j.children.forEach(c => { if (c.isMesh) meshes.push(c); });
      });

      const intersects = raycaster.intersectObjects(meshes, false);
      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const jname = hit.userData.jointName || hit.parent?.name;
        if (jname && jointMap[jname]) {
          selectJoint(jname);
        }
      } else {
        deselectJoint();
      }
    }

    renderer.domElement.addEventListener('pointerdown', onPointerDown);
    renderer.domElement.addEventListener('pointermove', onPointerMove);
    renderer.domElement.addEventListener('pointerup', onPointerUp);

    // Keyboard shortcuts
    function onKeyDown(e) {
      if (e.code === 'KeyX') { setMode('translate'); e.preventDefault(); }
      if (e.code === 'KeyR') { setMode('rotate'); e.preventDefault(); }
      if (e.code === 'KeyZ' && (e.ctrlKey || e.metaKey) && !e.shiftKey) { doUndo(); e.preventDefault(); }
      if (e.code === 'KeyZ' && (e.ctrlKey || e.metaKey) && e.shiftKey) { doRedo(); e.preventDefault(); }
      if (e.code === 'KeyY' && (e.ctrlKey || e.metaKey)) { doRedo(); e.preventDefault(); }
      if (e.code === 'Escape') { deselectJoint(); }
    }
    document.addEventListener('keydown', onKeyDown);

    // Animation loop
    function animate() {
      animId = requestAnimationFrame(animate);
      orbitControls.update();
      bodyRoot.updateMatrixWorld(true);
      updateAllLinks(THREE);
      renderer.render(scene, camera);
    }
    animate();

    // Handle viewport resize
    const resizeObs = new ResizeObserver(() => {
      if (!renderer || !camera) return;
      const w = viewport.clientWidth;
      const h = viewport.clientHeight;
      if (w === 0 || h === 0) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    resizeObs.observe(viewport);

    // Store cleanup refs
    viewport._cleanup = () => {
      renderer.domElement.removeEventListener('pointerdown', onPointerDown);
      renderer.domElement.removeEventListener('pointermove', onPointerMove);
      renderer.domElement.removeEventListener('pointerup', onPointerUp);
      document.removeEventListener('keydown', onKeyDown);
      resizeObs.disconnect();
      if (animId) cancelAnimationFrame(animId);
      if (transformControl) transformControl.dispose();
      if (orbitControls) orbitControls.dispose();
      if (renderer) renderer.dispose();
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // UI EVENT HANDLERS
  // ═══════════════════════════════════════════════════════════════════
  function stopProp(e) { e.stopPropagation(); }

  // Preset buttons
  rootEl.querySelectorAll('[data-preset]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      applyPreset(btn.dataset.preset);
    });
  });

  // Capture buttons
  rootEl.querySelectorAll('[data-cap]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      let img = null;
      const type = btn.dataset.cap;
      if (type === 'pose') img = capturePoseImage();
      else if (type === 'depth') img = captureDepthMap();
      else if (type === 'normal') img = captureNormalMap();

      if (img) {
        const extra = {};
        if (type === 'pose') extra.captured_image = img;
        else if (type === 'depth') extra.depth_map = img;
        else if (type === 'normal') extra.normal_map = img;
        emitChange(extra);
      }
    });
  });

  // Action buttons
  rootEl.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = btn.dataset.action;
      if (action === 'undo') doUndo();
      else if (action === 'redo') doRedo();
      else if (action === 'save') {
        const data = JSON.stringify(getSceneState(), null, 2);
        const blob = new Blob([data], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'openpose_scene_' + Date.now() + '.json';
        a.click();
        URL.revokeObjectURL(url);
      }
      else if (action === 'load') {
        fileInput.click();
      }
    });
  });

  // File input for load
  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        pushUndo();
        const data = JSON.parse(ev.target.result);
        restoreSceneState(data);
        buildParamSliders();
        emitChange();
      } catch (err) { console.error('Failed to load scene:', err); }
    };
    reader.readAsText(file);
    fileInput.value = '';
  });

  // Mode buttons
  rootEl.querySelectorAll('.op3d-mode-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      setMode(btn.dataset.mode);
    });
  });

  // Grid toggle
  const gridToggle = rootEl.querySelector('.op3d-grid-toggle');
  if (gridToggle) {
    gridToggle.addEventListener('change', (e) => {
      e.stopPropagation();
      if (gridHelper) gridHelper.visible = gridToggle.checked;
      if (axesHelper) axesHelper.visible = gridToggle.checked;
    });
  }

  // Body param sliders
  slidersDiv.addEventListener('input', (e) => {
    e.stopPropagation();
    const slider = e.target;
    if (!slider.classList.contains('op3d-slider')) return;
    const pname = slider.dataset.param;
    const val = parseFloat(slider.value);
    const param = bodyParams.find(p => p.name === pname);
    if (param) {
      pushUndo();
      param.set(val);
      // Update display
      const valSpan = slidersDiv.querySelector('.op3d-val[data-param="' + pname + '"]');
      if (valSpan) valSpan.textContent = Math.round(val);
      emitChange();
    }
  });

  // Prevent node drag on our root
  rootEl.addEventListener('pointerdown', stopProp);
  rootEl.addEventListener('mousedown', stopProp);

  // ═══════════════════════════════════════════════════════════════════
  // INIT
  // ═══════════════════════════════════════════════════════════════════
  initScene().catch(err => {
    console.error('OpenPose3DEditor init failed:', err);
    viewport.innerHTML = '<div style="color:red;padding:20px;text-align:center;">Failed to initialize 3D editor. Check console.</div>';
  });

  // ═══════════════════════════════════════════════════════════════════
  // CLEANUP
  // ═══════════════════════════════════════════════════════════════════
  return () => {
    if (viewport._cleanup) viewport._cleanup();
    rootEl.removeEventListener('pointerdown', stopProp);
    rootEl.removeEventListener('mousedown', stopProp);
  };
}
