"""OpenPose 3D Editor – Main widget node for interactive pose editing."""

import json
import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget

logger = logging.getLogger(__name__)

# Default T-pose joint world positions (matching the widget's initial geometry)
DEFAULT_JOINTS = {
    "nose":            [0, 155, 10],
    "neck":            [0, 140, 0],
    "right_shoulder":  [-18, 140, 0],
    "right_elbow":     [-42, 140, 0],
    "right_wrist":     [-66, 140, 0],
    "left_shoulder":   [18, 140, 0],
    "left_elbow":      [42, 140, 0],
    "left_wrist":      [66, 140, 0],
    "right_hip":       [-10, 95, 0],
    "right_knee":      [-10, 55, 0],
    "right_ankle":     [-10, 19, 0],
    "left_hip":        [10, 95, 0],
    "left_knee":       [10, 55, 0],
    "left_ankle":      [10, 19, 0],
    "right_eye":       [-4, 159, 10],
    "left_eye":        [4, 159, 10],
    "right_ear":       [-7, 157, 5],
    "left_ear":        [7, 157, 5],
}


class PoseEditorNode(DataNode):
    """Interactive 3D OpenPose skeleton editor.

    Features (all inside the widget):
    - 18 draggable joints with full rotation/translation gizmos
    - Camera orbit, zoom, pan (OrbitControls)
    - Body parameter sliders (shoulder width, arm/leg length, torso height)
    - Preset poses: T-Pose, A-Pose, Walking, Sitting, Relaxed
    - Capture pose image (skeleton on black background)
    - Depth map & Normal map capture
    - Save/Load scene as JSON
    - Undo/Redo (Ctrl+Z / Ctrl+Y)

    Outputs:
    - joints_json: All 18 keypoint positions as JSON
    - captured_image: Base64 PNG data URL of captured pose (when captured)
    - depth_map: Base64 PNG data URL of depth map (when captured)
    - normal_map: Base64 PNG data URL of normal map (when captured)
    - scene_json: Full scene state for save/restore
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "PoseEditor",
            "description": "Interactive 3D OpenPose skeleton editor with full pose manipulation",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        # Main widget parameter
        self.add_parameter(
            Parameter(
                name="pose_editor",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={"joints": DEFAULT_JOINTS},
                tooltip="3D OpenPose editor. Click joints to select, drag gizmos to pose. Use toolbar for presets, capture, and save/load.",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="OpenPose3DEditor", library="OpenPose 3D Editor Library")},
            )
        )

        # Output: joint positions as JSON
        self.add_parameter(
            Parameter(
                name="joints_json",
                output_type="str",
                tooltip="All 18 keypoint world positions as JSON string",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Joint positions JSON"},
            )
        )

        # Output: captured pose image
        self.add_parameter(
            Parameter(
                name="captured_image",
                output_type="str",
                tooltip="Base64 PNG data URL of the captured pose image (skeleton on black bg). Click '📷 Pose' in the widget to capture.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Capture a pose image using the 📷 button"},
            )
        )

        # Output: depth map
        self.add_parameter(
            Parameter(
                name="depth_map",
                output_type="str",
                tooltip="Base64 PNG data URL of the depth map. Click '📷 Depth' in the widget to capture.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Capture depth map using the 📷 button"},
            )
        )

        # Output: normal map
        self.add_parameter(
            Parameter(
                name="normal_map",
                output_type="str",
                tooltip="Base64 PNG data URL of the normal map. Click '📷 Normal' in the widget to capture.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Capture normal map using the 📷 button"},
            )
        )

        # Output: scene JSON for save/restore
        self.add_parameter(
            Parameter(
                name="scene_json",
                output_type="str",
                tooltip="Full scene state as JSON — can be loaded back into the editor",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Scene state JSON"},
            )
        )

        # Output: joint count
        self.add_parameter(
            Parameter(
                name="joint_count",
                output_type="int",
                tooltip="Number of joints in the current pose",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        pose_data = self.parameter_values.get("pose_editor", {})

        joints = DEFAULT_JOINTS
        captured_image = None
        depth_map = None
        normal_map = None
        scene_json = None

        if isinstance(pose_data, dict):
            joints = pose_data.get("joints", DEFAULT_JOINTS)
            captured_image = pose_data.get("captured_image")
            depth_map = pose_data.get("depth_map")
            normal_map = pose_data.get("normal_map")
            scene_json = pose_data.get("scene_json")

        # Output everything
        self.parameter_output_values["pose_editor"] = {"joints": joints}
        self.parameter_output_values["joints_json"] = json.dumps(joints, indent=2)
        self.parameter_output_values["captured_image"] = captured_image or ""
        self.parameter_output_values["depth_map"] = depth_map or ""
        self.parameter_output_values["normal_map"] = normal_map or ""
        self.parameter_output_values["scene_json"] = scene_json or ""
        self.parameter_output_values["joint_count"] = len(joints) if isinstance(joints, dict) else 0

        logger.info(f"PoseEditorNode: {len(joints)} joints, image={'yes' if captured_image else 'no'}")
