"""Load Pose Scene – Load a saved pose scene JSON file into the editor."""

import json
import logging
import os
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger(__name__)


class LoadPoseScene(ControlNode):
    """Load a previously saved pose scene from a JSON file.

    The scene JSON can be connected to the Pose Editor node's input to restore
    the full pose state including joint rotations, body parameters, and camera position.
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "PoseTools",
            "description": "Load a saved pose scene from a JSON file",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        # Input: file path
        self.add_parameter(
            Parameter(
                name="file_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Path to a saved pose scene JSON file",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "Path to scene.json"},
            )
        )

        # Output: scene JSON string
        self.add_parameter(
            Parameter(
                name="scene_json",
                output_type="str",
                tooltip="Scene state as JSON string — connect to the Pose Editor's scene_json input or use to inspect the pose data",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Scene JSON output"},
            )
        )

        # Output: joints dict
        self.add_parameter(
            Parameter(
                name="joints_json",
                output_type="str",
                tooltip="Joint positions extracted from the scene as JSON string",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Joint positions JSON"},
            )
        )

        # Output: success
        self.add_parameter(
            Parameter(
                name="success",
                output_type="bool",
                tooltip="Whether the file was loaded successfully",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        file_path = self.parameter_values.get("file_path", "")

        if not file_path or not os.path.isfile(file_path):
            logger.warning(f"LoadPoseScene: File not found: {file_path}")
            self.parameter_output_values["scene_json"] = ""
            self.parameter_output_values["joints_json"] = ""
            self.parameter_output_values["success"] = False
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw = f.read()

            # Validate JSON
            data = json.loads(raw)

            # Extract joints if present
            joints = data.get("joints", {})
            # Joints might be stored as position/rotation pairs, extract world positions if available
            joints_output = {}
            for name, jdata in joints.items():
                if isinstance(jdata, dict) and "position" in jdata:
                    joints_output[name] = jdata["position"]
                elif isinstance(jdata, list):
                    joints_output[name] = jdata

            self.parameter_output_values["scene_json"] = raw
            self.parameter_output_values["joints_json"] = json.dumps(joints_output, indent=2) if joints_output else ""
            self.parameter_output_values["success"] = True
            logger.info(f"LoadPoseScene: Loaded scene from {file_path} ({len(raw)} bytes)")

        except Exception as e:
            logger.error(f"LoadPoseScene: Failed to load: {e}")
            self.parameter_output_values["scene_json"] = ""
            self.parameter_output_values["joints_json"] = ""
            self.parameter_output_values["success"] = False
