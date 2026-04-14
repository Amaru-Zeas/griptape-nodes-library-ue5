"""
Blender HTTP bridge for Griptape Nodes camera control.

Run this script inside Blender's Scripting workspace:
1) Open Text Editor in Blender.
2) Load this file.
3) Click "Run Script".
"""

import json
import os
import queue
import threading
import traceback
import base64
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import bpy

HOST = os.getenv("BLENDER_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.getenv("BLENDER_BRIDGE_PORT", "8765"))

_server = None
_server_thread = None
_main_thread_queue = queue.Queue()
_main_thread_timer_active = False


def _main_thread_pump():
    """Execute queued Blender ops on Blender's main thread.

    Blender's bpy API is not thread-safe. HTTP request threads enqueue work here.
    """
    global _main_thread_timer_active
    while True:
        try:
            fn, done_event, result = _main_thread_queue.get_nowait()
        except queue.Empty:
            break

        try:
            result["value"] = fn()
        except Exception as exc:
            result["error"] = exc
            result["traceback"] = traceback.format_exc()
        finally:
            done_event.set()

    # Keep timer alive while bridge is running.
    return 0.01 if _main_thread_timer_active else None


def _ensure_main_thread_timer():
    global _main_thread_timer_active
    if _main_thread_timer_active:
        return
    _main_thread_timer_active = True
    bpy.app.timers.register(_main_thread_pump, first_interval=0.01)


def _run_on_main_thread(fn, timeout: float = 4.0):
    """Run a callable safely on Blender's main thread and wait for result."""
    if threading.current_thread() is threading.main_thread():
        return fn()

    done_event = threading.Event()
    result = {}
    _main_thread_queue.put((fn, done_event, result))

    if not done_event.wait(timeout):
        raise TimeoutError("Timed out waiting for Blender main-thread execution.")
    if "error" in result:
        raise RuntimeError(f"{result['error']}\n{result.get('traceback', '')}")
    return result.get("value")


def _camera_payload(camera_obj: bpy.types.Object) -> dict:
    loc = camera_obj.location
    rot = camera_obj.rotation_euler
    fov = float(camera_obj.data.angle) if camera_obj.data and hasattr(camera_obj.data, "angle") else None
    return {
        "name": camera_obj.name,
        "location": {"x": float(loc.x), "y": float(loc.y), "z": float(loc.z)},
        "rotation_euler": {"x": float(rot.x), "y": float(rot.y), "z": float(rot.z)},
        "fov_radians": fov,
    }


def _resolve_camera(name: str | None) -> bpy.types.Object:
    if name:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == "CAMERA":
            return obj
    scene_cam = bpy.context.scene.camera
    if scene_cam and scene_cam.type == "CAMERA":
        return scene_cam
    # Last fallback: first camera in scene.
    for obj in bpy.data.objects:
        if obj.type == "CAMERA":
            return obj
    raise RuntimeError("No camera found in current Blender file.")


def _list_cameras() -> list[str]:
    return [obj.name for obj in bpy.data.objects if obj.type == "CAMERA"]


def _capture_viewport_snapshot(
    camera_name: str | None,
    width: int = 1280,
    height: int = 720,
    keep_scene_camera: bool = True,
) -> dict:
    scene = bpy.context.scene
    prev_camera = scene.camera
    prev_x = scene.render.resolution_x
    prev_y = scene.render.resolution_y
    prev_pct = scene.render.resolution_percentage

    target_camera = _resolve_camera(camera_name)

    # Use an OpenGL viewport render from the selected camera.
    # This is fast and close to "what you currently see", not a full final render.
    scene.camera = target_camera
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.resolution_percentage = 100

    tmp_path = None
    try:
        bpy.ops.render.opengl(animation=False, sequencer=False, view_context=False)
        render_result = bpy.data.images.get("Render Result")
        if not render_result:
            raise RuntimeError("No 'Render Result' image available after viewport capture.")

        with tempfile.NamedTemporaryFile(prefix="gtn_cam_", suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        render_result.save_render(tmp_path)
        with open(tmp_path, "rb") as f:
            raw = f.read()
        data_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")

        return {
            "ok": True,
            "camera": target_camera.name,
            "width": int(width),
            "height": int(height),
            "image_data_url": data_url,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        scene.render.resolution_x = prev_x
        scene.render.resolution_y = prev_y
        scene.render.resolution_percentage = prev_pct
        if not keep_scene_camera:
            scene.camera = prev_camera


class _Handler(BaseHTTPRequestHandler):
    def _set_headers(self, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _json(self, payload: dict, code: int = 200) -> None:
        self._set_headers(code)
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/health"):
            self._json({"ok": True, "message": "Blender bridge alive"})
            return

        if parsed.path == "/cameras":
            try:
                self._json(_run_on_main_thread(lambda: {"ok": True, "cameras": _list_cameras()}))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return

        if parsed.path == "/camera/get":
            query = parse_qs(parsed.query)
            name = (query.get("name", [None])[0] or None)
            try:
                def _get():
                    cam = _resolve_camera(name)
                    return {"ok": True, "camera": _camera_payload(cam)}

                self._json(_run_on_main_thread(_get))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return

        if parsed.path == "/viewport/snapshot":
            query = parse_qs(parsed.query)
            name = (query.get("camera", [None])[0] or None)
            width = int((query.get("width", ["1280"])[0] or "1280"))
            height = int((query.get("height", ["720"])[0] or "720"))
            keep_scene_camera = (query.get("keep_scene_camera", ["true"])[0] or "true").lower() != "false"
            try:
                def _snap():
                    return _capture_viewport_snapshot(
                        camera_name=name,
                        width=width,
                        height=height,
                        keep_scene_camera=keep_scene_camera,
                    )

                self._json(_run_on_main_thread(_snap, timeout=12.0))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return

        self._json({"ok": False, "error": f"Unknown route: {parsed.path}"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/camera/set":
            self._json({"ok": False, "error": f"Unknown route: {parsed.path}"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body) if body else {}
            name = payload.get("name")
            location = payload.get("location", {})
            rotation = payload.get("rotation_euler", {})

            def _set():
                cam = _resolve_camera(name)
                cam.location.x = float(location.get("x", cam.location.x))
                cam.location.y = float(location.get("y", cam.location.y))
                cam.location.z = float(location.get("z", cam.location.z))
                cam.rotation_euler.x = float(rotation.get("x", cam.rotation_euler.x))
                cam.rotation_euler.y = float(rotation.get("y", cam.rotation_euler.y))
                cam.rotation_euler.z = float(rotation.get("z", cam.rotation_euler.z))

                bpy.context.view_layer.update()
                return {"ok": True, "camera": _camera_payload(cam)}

            self._json(_run_on_main_thread(_set))
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 400)

    def log_message(self, format, *args):
        # Reduce console noise in Blender.
        return


def stop_bridge() -> None:
    global _server, _server_thread, _main_thread_timer_active
    if _server:
        _server.shutdown()
        _server.server_close()
        _server = None
    if _server_thread:
        _server_thread = None
    _main_thread_timer_active = False
    if bpy.app.timers.is_registered(_main_thread_pump):
        bpy.app.timers.unregister(_main_thread_pump)
    print("[BlenderBridge] stopped")


def start_bridge(host: str = HOST, port: int = PORT) -> None:
    global _server, _server_thread
    if _server:
        print(f"[BlenderBridge] already running on http://{host}:{port}")
        return
    _ensure_main_thread_timer()
    _server = ThreadingHTTPServer((host, port), _Handler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    print(f"[BlenderBridge] running on http://{host}:{port}")


start_bridge()
