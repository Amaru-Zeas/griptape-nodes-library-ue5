# UE5 Camera Control Library for Griptape Nodes

Control and **see** an Unreal Engine 5 camera directly from Griptape Nodes. The widget renders a **live video stream** from UE5 via Pixel Streaming, so you navigate the scene as if you were inside UE5 -- plus programmatic camera controls for pipeline automation.

## Features

- **Live UE5 Viewport** - See the actual rendered camera view inside the widget via Pixel Streaming
- **Real-Time Navigation** - Arrow/WASD-style controls move the camera and the live view updates
- **Two Camera Modes**:
  - **Viewport Mode** - Control the UE5 editor viewport camera
  - **Actor Mode** - Control a specific CameraActor/CineCameraActor
- **Pipeline Integration** - Use node inputs/outputs for automated camera workflows

---

## UE5 Setup (Quick Start)

Based on the [official Pixel Streaming in Editor docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/pixel-streaming-in-editor), the setup is straightforward -- **no separate server needed**.

### Step 1: Enable Plugins (one-time)

Open UE5 > **Edit > Plugins**, enable these, then restart:

| Plugin | Purpose |
|--------|---------|
| **Pixel Streaming** | Streams the editor viewport as video |
| **Remote Control API** | HTTP API for camera position control |
| **Editor Scripting Utilities** | Viewport camera get/set functions |

### Step 2: Enable CORS (one-time)

**Edit > Project Settings > Plugins > Web Remote Control**:
- Check **Enable CORS**
- Set Allowed Origins to `*`

### Step 3: Start Streaming (every session)

1. In UE5, look for the **Pixel Streaming** menu on the toolbar
2. Click **"Stream Level Editor"** (streams just the viewport, not the full editor UI)
   - UE5 starts an **embedded signalling server** automatically -- no external server needed
3. Verify: open `http://127.0.0.1` in a browser -- you should see the live editor viewport

> **Note:** Default viewer port is **80** on Windows, **8080** on Linux. If port 80 is taken, check the Pixel Streaming toolbar settings for "Embedded Signalling Server Options" to change ports.

That's it! The stream URL for the widget is `http://127.0.0.1` (or `http://127.0.0.1:8080` on Linux).

---

## Testing in Griptape Nodes

1. **Refresh libraries** in Griptape Nodes to pick up the UE5 Camera Control Library
2. Add the **UE5 Camera Control** node to your canvas
3. In the widget:
   - Enter `http://127.0.0.1` in the **Stream** field and click **Load Stream**
   - The live UE5 viewport should appear in the widget
   - Click **Test** to connect to the Remote Control API (port 30010)
   - Green dot = connected
4. Use navigation buttons or type exact coordinates
5. Click **Sync from UE5** to read the current camera position
6. Click **Push to UE5** to apply your coordinates

The Pixel Streaming iframe also forwards mouse/keyboard input, so you can interact with the viewport directly by clicking/dragging inside the live view.

---

## Alternative: Standalone Game / Packaged Build

If you prefer to stream a packaged game instead of the editor:

1. Get the Pixel Streaming Infrastructure servers from [GitHub](https://github.com/EpicGamesExt/PixelStreamingInfrastructure)
   - Or run `get_ps_servers.bat` from `Engine\Plugins\Media\PixelStreaming\Resources\WebServers\`
2. Start the signalling server: `SignallingWebServer\platform_scripts\cmd\start_with_stun.bat`
3. Launch your game with: `-PixelStreamingURL=ws://127.0.0.1:8888`
4. Connect at `http://127.0.0.1`

See the [Getting Started guide](https://dev.epicgames.com/documentation/en-us/unreal-engine/getting-started-with-pixel-streaming-in-unreal-engine) for full details.

---

## Nodes

### UE5 Connect

Simple connection test node.

| Parameter | Type | Description |
|-----------|------|-------------|
| host | str | UE5 host (default: `localhost`) |
| port | int | Remote Control API port (default: `30010`) |
| **connected** | bool | Output: is UE5 reachable |
| **connection_url** | str | Output: base API URL |
| **status_message** | str | Output: status text |

### UE5 Camera Control

Live viewport + interactive camera controls.

| Parameter | Type | Description |
|-----------|------|-------------|
| host | str | UE5 host |
| port | int | Remote Control API port |
| stream_url | str | Pixel Streaming URL (default: `http://localhost:80`) |
| camera_mode | str | `viewport` or `actor` |
| actor_path | str | CameraActor object path (actor mode) |
| action | str | `get` or `set` (for pipeline processing) |
| pos_x/y/z | float | Camera position |
| rot_pitch/yaw/roll | float | Camera rotation (degrees) |
| **out_position** | dict | Output: `{X, Y, Z}` |
| **out_rotation** | dict | Output: `{Pitch, Yaw, Roll}` |
| **status** | str | Output: result message |

---

## Widget Layout

```
┌──────────────────────────────────────┐
│  ┌────────────────────────────────┐  │
│  │                                │  │
│  │   Live UE5 Viewport            │  │
│  │   (Pixel Streaming)            │  │
│  │                                │  │
│  └────────────────────────────────┘  │
│  Stream: [http://127.0.0.1] [Load]  │
│  ● Host:Port  Mode  [Test]          │
│  Pos X[..] Y[..] Z[..]   [▲][▲]    │
│  Rot P[..] Y[..] R[..]  [◄][►][▼]  │
│  [Sync from UE5] [Push to UE5]      │
└──────────────────────────────────────┘
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No "Pixel Streaming" toolbar in UE5 | Enable the Pixel Streaming plugin and restart |
| Stream loads blank / won't connect | Check `http://127.0.0.1` in a regular browser first |
| Port 80 already in use | Change the embedded signalling server port in the PS toolbar settings |
| Widget shows stream but nav buttons don't move camera | Click **Test** to connect the Remote Control API (separate from Pixel Streaming) |
| "Get camera failed" | Enable **Editor Scripting Utilities** plugin |
| CORS error in browser console | Enable CORS in Project Settings > Web Remote Control |

## References

- [Pixel Streaming in Unreal Engine](https://dev.epicgames.com/documentation/en-us/unreal-engine/pixel-streaming-in-unreal-engine)
- [Pixel Streaming in Editor](https://dev.epicgames.com/documentation/en-us/unreal-engine/pixel-streaming-in-editor)
- [Getting Started with Pixel Streaming](https://dev.epicgames.com/documentation/en-us/unreal-engine/getting-started-with-pixel-streaming-in-unreal-engine)
- [Pixel Streaming Infrastructure (GitHub)](https://github.com/EpicGamesExt/PixelStreamingInfrastructure)
