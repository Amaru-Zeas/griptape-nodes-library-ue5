# Blender Camera Control Library for Griptape Nodes

Build a UE5-camera-style workflow for Blender in GTN:
- Connect to Blender from Griptape Nodes
- Read and set camera transform (position + Euler rotation)
- Optionally embed a live viewport stream URL in-node

## Important: Blender and "Pixel Streaming"

Blender does **not** provide a UE5 Pixel Streaming equivalent out of the box.

You can still achieve a very similar effect with this split setup:
1. **Control channel**: HTTP bridge script running in Blender (`blender_bridge_server.py`)
2. **Video channel**: Any streamable viewport source (OBS + browser player, WebRTC relay, NDI web gateway, etc.) loaded in the `Blender Viewport` widget

## Full Blender UI Inside GTN (closest to UE5 flow)

If you want to navigate Blender UI directly in GTN (panels, viewport navigation, transforms, shortcuts), run Blender in a browser-enabled remote session and embed that URL in `Blender Viewport`.

### Recommended: Docker `linuxserver/blender` (web UI)

1. Install Docker Desktop.
2. Run:

```powershell
docker pull lscr.io/linuxserver/blender:latest
docker run -d --name gtn-blender --restart unless-stopped `
  -e PUID=1000 -e PGID=1000 -e TZ=Etc/UTC `
  -e BLENDER_BRIDGE_HOST=0.0.0.0 -e BLENDER_BRIDGE_PORT=8765 `
  -p 3000:3000 -p 3001:3001 -p 8765:8765 `
  --shm-size="1gb" `
  -v blender-config:/config `
  -v "a:\GriptapeSketchFab:/workspace" `
  lscr.io/linuxserver/blender:latest
```

3. Open Blender in browser:
   - [http://127.0.0.1:3000](http://127.0.0.1:3000)
4. In that Blender session, run:
   - `/workspace/griptape-nodes-library-blendercamera/blender_camera_nodes/blender_bridge_server.py`
5. In GTN:
   - `Blender Viewport` URL: `http://127.0.0.1:3000` (full interactive Blender UI)
   - `Blender Connect` host/port: `127.0.0.1` / `8765`
   - `Blender Camera Control` for programmatic get/set

This gives you both:
- full interactive Blender UI inside GTN
- API camera control through the bridge node

### Stop / start container

```powershell
docker stop gtn-blender
docker start gtn-blender
```

---

## Included Nodes

### Blender Connect
- Tests whether the Blender bridge is reachable.
- Outputs: `connected`, `connection_url`, `status_message`, `bridge_config`
- `bridge_config` can be connected to other Blender nodes so you set host/port once.

### Blender Camera Control
- Action `get`: read camera transform from Blender
- Action `set`: push transform to Blender
- Supports selecting camera by object name (`camera_name`)
- If `camera_name` is empty, it auto-uses active/first camera.
- Outputs: `out_position`, `out_rotation`, `status`

### Blender Viewport
- Lightweight iframe widget for your stream URL
- Useful for monitoring while driving camera transforms from GTN

### Blender Camera View Capture
- Shows a camera dropdown (auto-loaded from Blender)
- Captures a fast viewport snapshot from selected camera
- Outputs `image_data_url` (PNG data URL) without doing a full final render
- Good for "what camera sees right now" checks in workflows
- Accepts `bridge_config` input from `Blender Connect`
- Also accepts `viewport_url` from `Blender Viewport.current_url` and auto-routes to bridge API (`:8765`)

---

## Blender Setup (Bridge Script)

1. Open Blender
2. Go to **Scripting** workspace
3. Open `blender_camera_nodes/blender_bridge_server.py`
4. Click **Run Script**
5. Verify in a browser:
   - [http://127.0.0.1:8765/health](http://127.0.0.1:8765/health)

Expected response:
```json
{"ok": true, "message": "Blender bridge alive"}
```

## GTN Setup

1. Add library path in GTN Settings > Libraries:
   - `<workspace>/griptape-nodes-library-blendercamera/blender_camera_nodes/griptape_nodes_library.json`
2. Refresh libraries
3. Add nodes:
   - `Blender Connect`
   - `Blender Camera Control`
   - `Blender Viewport` (optional)

---

## Minimal Test Flow

1. `Blender Connect`
   - host: `127.0.0.1`
   - port: `8765`
2. `Blender Camera Control`
   - connect `bridge_config` from `Blender Connect`
   - action: `get`
   - camera_name: (optional; blank = active/first camera)
3. Run flow and confirm `out_position` / `out_rotation` populate.
4. Change action to `set`, edit values, run again, and watch Blender camera move.
5. `Blender Camera View Capture`
   - connect `bridge_config` from `Blender Connect`
   - choose camera from dropdown
   - run flow to produce `image_data_url`
   - use this output in downstream image nodes

## After Updating This Library

If GTN is already open, do:
1. Refresh libraries in GTN
2. Re-run `blender_bridge_server.py` in Blender so new `/cameras` and `/viewport/snapshot` routes are active

---

## Notes

- Rotation values are in **radians** (native Blender Euler values).
- If `camera_name` is empty or not found, the bridge falls back to scene active camera.
- If no scene camera is active, it picks the first camera object found.

## Troubleshooting

- **Cannot reach bridge**
  - Re-run `blender_bridge_server.py` inside Blender.
  - Check that port `8765` is not blocked by another process.
- **Camera not found**
  - Confirm camera object name in Blender Outliner.
- **No live viewport in node**
  - Ensure your stream URL works in a normal browser first, then paste it in `Blender Viewport`.

