"""Blender Camera Control node - get/set camera transforms over HTTP."""

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode

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


def _get_camera(host: str, port: int, camera_name: str) -> dict[str, Any]:
    url = f"{_base_url(host, port)}/camera/get"
    resp = requests.get(url, params={"name": camera_name}, timeout=5)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


def _set_camera(
    host: str,
    port: int,
    camera_name: str,
    x: float,
    y: float,
    z: float,
    rot_x: float,
    rot_y: float,
    rot_z: float,
) -> dict[str, Any]:
    url = f"{_base_url(host, port)}/camera/set"
    payload = {
        "name": camera_name,
        "location": {"x": x, "y": y, "z": z},
        "rotation_euler": {"x": rot_x, "y": rot_y, "z": rot_z},
    }
    resp = requests.post(url, json=payload, timeout=5)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


class BlenderCameraControl(DataNode):
    """Get and set Blender camera transforms via a local bridge server."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "BlenderCamera",
            "description": "Get or set Blender camera transform",
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
                tooltip="Blender camera object name. Leave empty to use active/first camera.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="action",
                input_types=["str"],
                type="str",
                default_value="get",
                tooltip="Use 'get' to read camera, 'set' to push values",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="pos_x",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Camera location X",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="pos_y",
                input_types=["float"],
                type="float",
                default_value=-6.0,
                tooltip="Camera location Y",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="pos_z",
                input_types=["float"],
                type="float",
                default_value=3.0,
                tooltip="Camera location Z",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="rot_x",
                input_types=["float"],
                type="float",
                default_value=1.109,
                tooltip="Euler rotation X in radians",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="rot_y",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Euler rotation Y in radians",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="rot_z",
                input_types=["float"],
                type="float",
                default_value=0.814,
                tooltip="Euler rotation Z in radians",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="out_position",
                output_type="dict",
                tooltip="Camera position {x,y,z}",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="out_rotation",
                output_type="dict",
                tooltip="Camera Euler rotation {x,y,z}",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status",
                output_type="str",
                tooltip="Result message",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _read_values(self) -> tuple[str, int, str, str, float, float, float, float, float, float]:
        host = _normalize_host(str(self.parameter_values.get("host", "127.0.0.1")))
        port = int(self.parameter_values.get("port", 8765))
        bridge = self.parameter_values.get("bridge_config", {})
        if isinstance(bridge, dict):
            if bridge.get("host"):
                host = _normalize_host(str(bridge["host"]))
            if bridge.get("port"):
                port = int(bridge["port"])
            # Allow passing only connection_url.
            if bridge.get("connection_url"):
                try:
                    parsed = urlparse(str(bridge["connection_url"]))
                    if parsed.hostname:
                        host = _normalize_host(parsed.hostname)
                    if parsed.port:
                        port = int(parsed.port)
                except Exception:
                    pass

        action = str(self.parameter_values.get("action", "get")).strip().lower()
        camera_name = str(self.parameter_values.get("camera_name", "")).strip()
        x = float(self.parameter_values.get("pos_x", 0.0))
        y = float(self.parameter_values.get("pos_y", -6.0))
        z = float(self.parameter_values.get("pos_z", 3.0))
        rot_x = float(self.parameter_values.get("rot_x", 1.109))
        rot_y = float(self.parameter_values.get("rot_y", 0.0))
        rot_z = float(self.parameter_values.get("rot_z", 0.814))
        return host, port, action, camera_name, x, y, z, rot_x, rot_y, rot_z

    def _write_outputs(self, x: float, y: float, z: float, rot_x: float, rot_y: float, rot_z: float, status: str) -> None:
        self.parameter_output_values["out_position"] = {"x": x, "y": y, "z": z}
        self.parameter_output_values["out_rotation"] = {"x": rot_x, "y": rot_y, "z": rot_z}
        self.parameter_output_values["status"] = status

    def process(self) -> None:
        host, port, action, camera_name, x, y, z, rot_x, rot_y, rot_z = self._read_values()

        try:
            if action == "get":
                data = _get_camera(host, port, camera_name)
                cam = data.get("camera", {})
                loc = cam.get("location", {})
                rot = cam.get("rotation_euler", {})
                x = float(loc.get("x", x))
                y = float(loc.get("y", y))
                z = float(loc.get("z", z))
                rot_x = float(rot.get("x", rot_x))
                rot_y = float(rot.get("y", rot_y))
                rot_z = float(rot.get("z", rot_z))
                self._write_outputs(
                    x,
                    y,
                    z,
                    rot_x,
                    rot_y,
                    rot_z,
                    f"Fetched camera '{camera_name or 'active'}' from Blender.",
                )
                return

            if action == "set":
                _set_camera(host, port, camera_name, x, y, z, rot_x, rot_y, rot_z)
                self._write_outputs(
                    x,
                    y,
                    z,
                    rot_x,
                    rot_y,
                    rot_z,
                    (
                        f"Updated camera '{camera_name}' to "
                        f"pos=({x:.3f}, {y:.3f}, {z:.3f}) "
                        f"rot=({rot_x:.3f}, {rot_y:.3f}, {rot_z:.3f})."
                    ),
                )
                return

            self._write_outputs(x, y, z, rot_x, rot_y, rot_z, f"Unknown action '{action}'. Use 'get' or 'set'.")
        except requests.ConnectionError:
            self._write_outputs(
                x,
                y,
                z,
                rot_x,
                rot_y,
                rot_z,
                f"Cannot reach Blender bridge at {host}:{port}. Start the bridge script in Blender.",
            )
        except requests.HTTPError as exc:
            self._write_outputs(x, y, z, rot_x, rot_y, rot_z, f"Bridge API error: {exc}")
        except Exception as exc:
            logger.error("Blender camera control error: %s", exc, exc_info=True)
            self._write_outputs(x, y, z, rot_x, rot_y, rot_z, f"Error: {exc}")
