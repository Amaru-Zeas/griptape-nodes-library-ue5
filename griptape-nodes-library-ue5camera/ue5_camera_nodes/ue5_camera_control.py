"""UE5 Camera Control node - navigate and control cameras in Unreal Engine 5."""

import logging
import math
from typing import Any

import requests

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UE5 Remote Control API helpers
# ---------------------------------------------------------------------------

def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _call_ue5(host: str, port: int, object_path: str, function_name: str,
              parameters: dict | None = None, timeout: float = 5.0) -> dict:
    """Call a function on a UE5 object via the Remote Control API."""
    url = f"{_base_url(host, port)}/remote/object/call"
    body: dict[str, Any] = {
        "objectPath": object_path,
        "functionName": function_name,
        "generateTransaction": False,
    }
    if parameters:
        body["parameters"] = parameters

    resp = requests.put(url, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


def _set_property(host: str, port: int, object_path: str,
                  property_name: str, value: Any, timeout: float = 5.0) -> dict:
    """Set a property on a UE5 object via the Remote Control API."""
    url = f"{_base_url(host, port)}/remote/object/property"
    body = {
        "objectPath": object_path,
        "access": "WRITE_ACCESS",
        "propertyName": property_name,
        "propertyValue": value,
    }
    resp = requests.put(url, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


def _get_property(host: str, port: int, object_path: str,
                  property_name: str, timeout: float = 5.0) -> Any:
    """Get a property from a UE5 object via the Remote Control API."""
    url = f"{_base_url(host, port)}/remote/object/property"
    body = {
        "objectPath": object_path,
        "access": "READ_ACCESS",
        "propertyName": property_name,
    }
    resp = requests.put(url, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


# ---------------------------------------------------------------------------
# Editor viewport camera helpers
# ---------------------------------------------------------------------------

_EDITOR_LIB = "/Script/EditorScriptingUtilities.Default__EditorLevelLibrary"


def get_viewport_camera(host: str, port: int) -> dict:
    """Get the editor viewport camera location and rotation.

    Uses EditorLevelLibrary::GetLevelViewportCameraInfo() which returns
    the active viewport camera's location and rotation.
    """
    result = _call_ue5(host, port, _EDITOR_LIB,
                       "GetLevelViewportCameraInfo", {})
    # Response shape:
    #   { "ReturnValue": true,
    #     "CameraLocation": {"X":..., "Y":..., "Z":...},
    #     "CameraRotation": {"Pitch":..., "Yaw":..., "Roll":...} }
    return result


def set_viewport_camera(host: str, port: int,
                        x: float, y: float, z: float,
                        pitch: float, yaw: float, roll: float) -> dict:
    """Set the editor viewport camera location and rotation.

    Uses EditorLevelLibrary::SetLevelViewportCameraInfo().
    """
    return _call_ue5(host, port, _EDITOR_LIB,
                     "SetLevelViewportCameraInfo", {
                         "CameraLocation": {"X": x, "Y": y, "Z": z},
                         "CameraRotation": {"Pitch": pitch, "Yaw": yaw, "Roll": roll},
                     })


# ---------------------------------------------------------------------------
# Camera Actor helpers
# ---------------------------------------------------------------------------

def get_actor_camera(host: str, port: int, actor_path: str) -> dict:
    """Get a CameraActor's world location and rotation."""
    loc = _call_ue5(host, port, actor_path, "K2_GetActorLocation")
    rot = _call_ue5(host, port, actor_path, "K2_GetActorRotation")
    return {
        "CameraLocation": loc.get("ReturnValue", {}),
        "CameraRotation": rot.get("ReturnValue", {}),
    }


def set_actor_camera(host: str, port: int, actor_path: str,
                     x: float, y: float, z: float,
                     pitch: float, yaw: float, roll: float) -> dict:
    """Set a CameraActor's world location and rotation."""
    _call_ue5(host, port, actor_path, "K2_SetActorLocation", {
        "NewLocation": {"X": x, "Y": y, "Z": z},
        "bSweep": False,
        "SweepHitResult": {},
        "bTeleport": True,
    })
    _call_ue5(host, port, actor_path, "K2_SetActorRotation", {
        "NewRotation": {"Pitch": pitch, "Yaw": yaw, "Roll": roll},
        "bTeleportPhysics": True,
    })
    return {"success": True}


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class UE5CameraControl(DataNode):
    """Navigate and control a camera in Unreal Engine 5 with a live viewport.

    The widget renders a **live video stream** from UE5 via Pixel Streaming,
    so you can see exactly what the UE5 camera sees and navigate as if you
    were inside UE5.

    Supports two camera control modes:
    - **Viewport**: Controls the editor's active viewport camera directly
      (requires Editor Scripting Utilities plugin).
    - **Actor**: Controls a specific CameraActor or CineCameraActor in the
      scene by its object path.

    **Live view** requires UE5 Pixel Streaming plugin enabled. The stream
    URL (e.g. http://localhost:80) is embedded in the widget as a live viewport.

    When the node processes (flow runs), it performs the selected action:
    - **get**: Fetches the current camera state from UE5.
    - **set**: Pushes the current position/rotation values to UE5.
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "UE5Camera",
            "description": "Navigate and control a UE5 camera",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        # --- Connection ---
        self.add_parameter(
            Parameter(
                name="host",
                input_types=["str"],
                type="str",
                default_value="localhost",
                tooltip="UE5 host address",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="port",
                input_types=["int"],
                type="int",
                default_value=30010,
                tooltip="UE5 Remote Control API port (default 30010)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # --- Pixel Streaming (live viewport) ---
        self.add_parameter(
            Parameter(
                name="stream_url",
                input_types=["str"],
                type="str",
                default_value="http://127.0.0.1",
                tooltip="Pixel Streaming URL for the live UE5 viewport. "
                        "In UE5: enable Pixel Streaming plugin, then toolbar > Stream Level Editor. "
                        "Default is http://127.0.0.1 (port 80) or http://127.0.0.1:8080 on Linux.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # --- Mode ---
        self.add_parameter(
            Parameter(
                name="camera_mode",
                input_types=["str"],
                type="str",
                default_value="viewport",
                tooltip="'viewport' = editor viewport camera, 'actor' = specific CameraActor",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="actor_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Object path of the CameraActor (e.g. /Game/Maps/Main.Main:PersistentLevel.CineCamera_0). Only used in 'actor' mode.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="action",
                input_types=["str"],
                type="str",
                default_value="get",
                tooltip="'get' = read camera from UE5, 'set' = push values to UE5",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # --- Position inputs ---
        self.add_parameter(
            Parameter(
                name="pos_x",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Camera X position (UE5 Forward axis)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="pos_y",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Camera Y position (UE5 Right axis)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="pos_z",
                input_types=["float"],
                type="float",
                default_value=200.0,
                tooltip="Camera Z position (UE5 Up axis)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # --- Rotation inputs ---
        self.add_parameter(
            Parameter(
                name="rot_pitch",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Camera pitch in degrees (positive = look up)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="rot_yaw",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Camera yaw in degrees (rotation around Z axis)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="rot_roll",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Camera roll in degrees (tilt)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # --- Widget ---
        self.add_parameter(
            Parameter(
                name="camera_widget",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={
                    "host": "localhost",
                    "port": 30010,
                    "streamUrl": "http://127.0.0.1",
                    "mode": "viewport",
                    "actorPath": "",
                    "posX": 0.0, "posY": 0.0, "posZ": 200.0,
                    "rotPitch": 0.0, "rotYaw": 0.0, "rotRoll": 0.0,
                    "step": 100.0,
                    "rotStep": 15.0,
                },
                tooltip="Interactive camera control panel",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="UE5CameraWidget", library="UE5 Camera Control Library")},
            )
        )

        # --- Outputs ---
        self.add_parameter(
            Parameter(
                name="out_position",
                output_type="dict",
                tooltip="Current camera position {X, Y, Z}",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="out_rotation",
                output_type="dict",
                tooltip="Current camera rotation {Pitch, Yaw, Roll}",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status",
                output_type="str",
                tooltip="Result status message",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_values(self) -> tuple:
        """Collect camera parameters from inputs and widget state."""
        host = str(self.parameter_values.get("host", "localhost")).strip()
        port = int(self.parameter_values.get("port", 30010))
        mode = str(self.parameter_values.get("camera_mode", "viewport")).strip().lower()
        actor_path = str(self.parameter_values.get("actor_path", "")).strip()
        action = str(self.parameter_values.get("action", "get")).strip().lower()

        # Position / rotation from node inputs
        x = float(self.parameter_values.get("pos_x", 0.0))
        y = float(self.parameter_values.get("pos_y", 0.0))
        z = float(self.parameter_values.get("pos_z", 200.0))
        pitch = float(self.parameter_values.get("rot_pitch", 0.0))
        yaw = float(self.parameter_values.get("rot_yaw", 0.0))
        roll = float(self.parameter_values.get("rot_roll", 0.0))

        # Widget state may override if the user was navigating interactively
        widget = self.parameter_values.get("camera_widget", {})
        if isinstance(widget, dict):
            # Only override from widget if the node inputs haven't been
            # explicitly connected (keep pipeline inputs as priority)
            if widget.get("posX") is not None:
                x = float(widget.get("posX", x))
                y = float(widget.get("posY", y))
                z = float(widget.get("posZ", z))
                pitch = float(widget.get("rotPitch", pitch))
                yaw = float(widget.get("rotYaw", yaw))
                roll = float(widget.get("rotRoll", roll))
            if widget.get("host"):
                host = str(widget["host"])
            if widget.get("port"):
                port = int(widget["port"])
            if widget.get("mode"):
                mode = str(widget["mode"]).lower()
            if widget.get("actorPath"):
                actor_path = str(widget["actorPath"])

        return host, port, mode, actor_path, action, x, y, z, pitch, yaw, roll

    def _update_outputs(self, x: float, y: float, z: float,
                        pitch: float, yaw: float, roll: float,
                        status: str, host: str, port: int,
                        mode: str, actor_path: str) -> None:
        """Push values to node outputs and sync the widget."""
        self.parameter_output_values["out_position"] = {"X": x, "Y": y, "Z": z}
        self.parameter_output_values["out_rotation"] = {"Pitch": pitch, "Yaw": yaw, "Roll": roll}
        self.parameter_output_values["status"] = status

        stream_url = str(self.parameter_values.get("stream_url", "http://127.0.0.1")).strip()
        widget_state = {
            "host": host,
            "port": port,
            "streamUrl": stream_url,
            "mode": mode,
            "actorPath": actor_path,
            "posX": x, "posY": y, "posZ": z,
            "rotPitch": pitch, "rotYaw": yaw, "rotRoll": roll,
            "step": 100.0,
            "rotStep": 15.0,
        }
        self.parameter_output_values["camera_widget"] = widget_state
        self.parameter_values["camera_widget"] = widget_state

    # ------------------------------------------------------------------
    # Process
    # ------------------------------------------------------------------

    def process(self) -> None:
        host, port, mode, actor_path, action, x, y, z, pitch, yaw, roll = self._read_values()

        try:
            if action == "get":
                # --- Fetch camera from UE5 ---
                if mode == "viewport":
                    result = get_viewport_camera(host, port)
                    loc = result.get("CameraLocation", {})
                    rot = result.get("CameraRotation", {})
                else:
                    if not actor_path:
                        self._update_outputs(x, y, z, pitch, yaw, roll,
                                             "Error: actor_path is required in 'actor' mode",
                                             host, port, mode, actor_path)
                        return
                    result = get_actor_camera(host, port, actor_path)
                    loc = result.get("CameraLocation", {})
                    rot = result.get("CameraRotation", {})

                x = float(loc.get("X", 0))
                y = float(loc.get("Y", 0))
                z = float(loc.get("Z", 0))
                pitch = float(rot.get("Pitch", 0))
                yaw = float(rot.get("Yaw", 0))
                roll = float(rot.get("Roll", 0))

                self._update_outputs(x, y, z, pitch, yaw, roll,
                                     f"Camera retrieved from UE5 ({mode})",
                                     host, port, mode, actor_path)

            elif action == "set":
                # --- Push camera to UE5 ---
                if mode == "viewport":
                    set_viewport_camera(host, port, x, y, z, pitch, yaw, roll)
                else:
                    if not actor_path:
                        self._update_outputs(x, y, z, pitch, yaw, roll,
                                             "Error: actor_path is required in 'actor' mode",
                                             host, port, mode, actor_path)
                        return
                    set_actor_camera(host, port, actor_path, x, y, z, pitch, yaw, roll)

                self._update_outputs(x, y, z, pitch, yaw, roll,
                                     f"Camera set in UE5 ({mode}) to "
                                     f"pos=({x:.1f}, {y:.1f}, {z:.1f}) "
                                     f"rot=({pitch:.1f}, {yaw:.1f}, {roll:.1f})",
                                     host, port, mode, actor_path)

            else:
                self._update_outputs(x, y, z, pitch, yaw, roll,
                                     f"Unknown action '{action}'. Use 'get' or 'set'.",
                                     host, port, mode, actor_path)

        except requests.ConnectionError:
            self._update_outputs(x, y, z, pitch, yaw, roll,
                                 f"Cannot reach UE5 at {host}:{port}. "
                                 "Is UE5 running with Remote Control API enabled?",
                                 host, port, mode, actor_path)
        except requests.HTTPError as exc:
            self._update_outputs(x, y, z, pitch, yaw, roll,
                                 f"UE5 API error: {exc}",
                                 host, port, mode, actor_path)
        except Exception as exc:
            logger.error("UE5 camera control error: %s", exc, exc_info=True)
            self._update_outputs(x, y, z, pitch, yaw, roll,
                                 f"Error: {exc}",
                                 host, port, mode, actor_path)
