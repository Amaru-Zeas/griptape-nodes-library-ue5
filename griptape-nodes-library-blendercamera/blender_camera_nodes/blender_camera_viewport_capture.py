"""Blender Camera Viewport Capture node.

Provides:
- camera dropdown population (via bridge /cameras)
- camera viewport snapshot output (via bridge /viewport/snapshot)
"""

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget

logger = logging.getLogger(__name__)


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _normalize_host(host: str) -> str:
    raw = (host or "").strip()
    if not raw:
        return "127.0.0.1"
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.hostname or "127.0.0.1"
    return raw.strip().strip("/")


def _get_cameras(host: str, port: int) -> list[str]:
    resp = requests.get(f"{_base_url(host, port)}/cameras", timeout=5)
    resp.raise_for_status()
    payload = resp.json() if resp.text else {}
    return payload.get("cameras", []) if isinstance(payload, dict) else []


def _capture_snapshot(
    host: str,
    port: int,
    camera: str,
    width: int,
    height: int,
    keep_scene_camera: bool,
) -> dict[str, Any]:
    params = {
        "camera": camera,
        "width": int(width),
        "height": int(height),
        "keep_scene_camera": "true" if keep_scene_camera else "false",
    }
    resp = requests.get(f"{_base_url(host, port)}/viewport/snapshot", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


class BlenderCameraViewportCapture(DataNode):
    """Capture current camera viewport image (non-final render)."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "BlenderCamera",
            "description": "Choose a Blender camera and capture viewport snapshot",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="host",
                input_types=["str"],
                type="str",
                default_value="127.0.0.1",
                tooltip="Blender bridge host",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="port",
                input_types=["int"],
                type="int",
                default_value=8765,
                tooltip="Blender bridge port",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="viewport_url",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional: connect Blender Viewport current_url. Host auto-detected; API port forced to 8765.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="bridge_config",
                input_types=["dict"],
                type="dict",
                default_value={},
                tooltip="Optional config from Blender Connect bridge_config output",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="camera_name",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Camera to preview/capture. Leave empty to auto-pick active/first camera.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                default_value=1280,
                tooltip="Snapshot width",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                default_value=720,
                tooltip="Snapshot height",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="keep_scene_camera",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="If true, selected camera remains scene active camera",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="capture",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="If true, captures a fresh snapshot on process",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="camera_view_widget",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={
                    "host": "127.0.0.1",
                    "port": 8765,
                    "selectedCamera": "Camera",
                    "cameraList": ["Camera"],
                    "imageDataUrl": "",
                    "status": "Ready",
                    "width": 1280,
                    "height": 720,
                },
                tooltip="Camera picker + viewport snapshot panel",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="BlenderCameraViewport", library="Blender Camera Control Library")},
            )
        )

        self.add_parameter(
            Parameter(
                name="camera_list",
                output_type="str",
                tooltip="Comma-separated cameras from Blender",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="selected_camera",
                output_type="str",
                tooltip="Camera used for latest snapshot",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="image_data_url",
                output_type="str",
                tooltip="Captured PNG as data URL",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status",
                output_type="str",
                tooltip="Operation status",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        host = _normalize_host(str(self.parameter_values.get("host", "127.0.0.1")))
        port = int(self.parameter_values.get("port", 8765))
        viewport_url = str(self.parameter_values.get("viewport_url", "")).strip()
        bridge = self.parameter_values.get("bridge_config", {})
        if isinstance(bridge, dict):
            if bridge.get("host"):
                host = _normalize_host(str(bridge["host"]))
            if bridge.get("port"):
                port = int(bridge["port"])
            if bridge.get("connection_url"):
                try:
                    parsed = urlparse(str(bridge["connection_url"]))
                    if parsed.hostname:
                        host = _normalize_host(parsed.hostname)
                    if parsed.port:
                        port = int(parsed.port)
                except Exception:
                    pass

        # Optional convenience wiring: use Blender Viewport.current_url
        if viewport_url:
            try:
                parsed_view = urlparse(viewport_url if "://" in viewport_url else f"http://{viewport_url}")
                if parsed_view.hostname:
                    host = _normalize_host(parsed_view.hostname)
                # Stream UI usually runs on 3000/3001, but bridge API is on 8765.
                port = 8765
            except Exception:
                pass

        # Guardrail: if stream port leaks into this node, auto-correct.
        if port in (3000, 3001):
            port = 8765

        selected = str(self.parameter_values.get("camera_name", "")).strip()
        width = int(self.parameter_values.get("width", 1280))
        height = int(self.parameter_values.get("height", 720))
        keep_scene_camera = bool(self.parameter_values.get("keep_scene_camera", True))
        should_capture = bool(self.parameter_values.get("capture", True))

        widget_state = self.parameter_values.get("camera_view_widget", {})
        if isinstance(widget_state, dict):
            selected = str(widget_state.get("selectedCamera", selected) or selected)
            width = int(widget_state.get("width", width))
            height = int(widget_state.get("height", height))
            if widget_state.get("host"):
                host = str(widget_state.get("host"))
            if widget_state.get("port"):
                port = int(widget_state.get("port"))

        image_data_url = ""
        status = "Ready"
        cameras: list[str] = []

        def _sync_widget_state() -> None:
            out_widget = {
                "host": host,
                "port": port,
                "selectedCamera": selected,
                "cameraList": cameras,
                "imageDataUrl": image_data_url,
                "status": status,
                "width": width,
                "height": height,
            }
            self.parameter_output_values["camera_view_widget"] = out_widget
            self.parameter_values["camera_view_widget"] = out_widget

        try:
            cameras = _get_cameras(host, port)
            if cameras and (not selected or selected not in cameras):
                selected = cameras[0]

            if should_capture:
                payload = _capture_snapshot(host, port, selected, width, height, keep_scene_camera)
                image_data_url = str(payload.get("image_data_url", "") or "")
                if payload.get("camera"):
                    selected = str(payload["camera"])
                status = f"Captured viewport snapshot from '{selected}' ({width}x{height})."
            else:
                status = "Capture disabled; camera list refreshed."

            self.parameter_output_values["camera_list"] = ", ".join(cameras)
            self.parameter_output_values["selected_camera"] = selected
            self.parameter_output_values["image_data_url"] = image_data_url
            self.parameter_output_values["status"] = status

            _sync_widget_state()
        except requests.ConnectionError:
            status = f"Cannot reach Blender bridge at {host}:{port}."
            self.parameter_output_values["status"] = status
            self.parameter_output_values["camera_list"] = ""
            self.parameter_output_values["selected_camera"] = selected
            self.parameter_output_values["image_data_url"] = image_data_url
            _sync_widget_state()
        except requests.HTTPError as exc:
            err = str(exc)
            if "404" in err and "/cameras" in err:
                status = (
                    f"Bridge on {host}:{port} is old (missing /cameras). "
                    "Re-run latest blender_bridge_server.py in Blender."
                )
            elif "404" in err and "/viewport/snapshot" in err:
                status = (
                    f"Bridge on {host}:{port} is old (missing /viewport/snapshot). "
                    "Re-run latest blender_bridge_server.py in Blender."
                )
            else:
                status = f"Bridge API error: {exc}"
            self.parameter_output_values["status"] = status
            self.parameter_output_values["camera_list"] = ", ".join(cameras)
            self.parameter_output_values["selected_camera"] = selected
            self.parameter_output_values["image_data_url"] = image_data_url
            _sync_widget_state()
        except Exception as exc:
            logger.error("Blender camera viewport capture error: %s", exc, exc_info=True)
            status = f"Error: {exc}"
            self.parameter_output_values["status"] = status
            self.parameter_output_values["camera_list"] = ", ".join(cameras)
            self.parameter_output_values["selected_camera"] = selected
            self.parameter_output_values["image_data_url"] = image_data_url
            _sync_widget_state()
