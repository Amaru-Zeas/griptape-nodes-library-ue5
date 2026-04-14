"""Pose to ControlNet – Convert 3D joint data to 2D OpenPose format for ControlNet."""

import json
import logging
import math
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger(__name__)

# OpenPose 18-keypoint order
KEYPOINT_ORDER = [
    "nose", "neck", "right_shoulder", "right_elbow", "right_wrist",
    "left_shoulder", "left_elbow", "left_wrist", "right_hip", "right_knee",
    "right_ankle", "left_hip", "left_knee", "left_ankle", "right_eye",
    "left_eye", "right_ear", "left_ear",
]

# Connection pairs for drawing
CONNECTIONS = [
    [1, 2], [1, 5], [2, 3], [3, 4], [5, 6], [6, 7],
    [1, 8], [8, 9], [9, 10], [1, 11], [11, 12], [12, 13],
    [0, 1], [0, 14], [14, 16], [0, 15], [15, 17],
]


class PoseToControlNet(ControlNode):
    """Convert 3D OpenPose joint positions to 2D format for ControlNet.

    Projects the 3D joint positions to 2D image coordinates using a simple
    orthographic projection. The output JSON follows the standard OpenPose
    format expected by ControlNet.

    The 2D coordinates are normalized to fit within the specified image dimensions.
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "PoseTools",
            "description": "Convert 3D pose joints to 2D OpenPose format for ControlNet",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        # Input: joints JSON
        self.add_parameter(
            Parameter(
                name="joints_json",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="3D joint positions JSON from the Pose Editor",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Connect to joints_json output"},
            )
        )

        # Input: image width
        self.add_parameter(
            Parameter(
                name="image_width",
                input_types=["int"],
                type="int",
                default_value=512,
                tooltip="Output image width in pixels",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Input: image height
        self.add_parameter(
            Parameter(
                name="image_height",
                input_types=["int"],
                type="int",
                default_value=768,
                tooltip="Output image height in pixels",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Input: view (front, side, top)
        self.add_parameter(
            Parameter(
                name="view",
                input_types=["str"],
                type="str",
                default_value="front",
                tooltip="Projection view: 'front' (XY), 'side' (ZY), or 'top' (XZ)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Output: OpenPose JSON
        self.add_parameter(
            Parameter(
                name="openpose_json",
                output_type="str",
                tooltip="Standard OpenPose format JSON with 2D keypoints for ControlNet",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "OpenPose JSON output"},
            )
        )

        # Output: keypoints array
        self.add_parameter(
            Parameter(
                name="keypoints_2d",
                output_type="str",
                tooltip="2D keypoints as [[x, y, confidence], ...] array",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True},
            )
        )

    def process(self) -> None:
        joints_json = self.parameter_values.get("joints_json", "")
        img_w = self.parameter_values.get("image_width", 512)
        img_h = self.parameter_values.get("image_height", 768)
        view = self.parameter_values.get("view", "front").lower()

        if not joints_json:
            self.parameter_output_values["openpose_json"] = ""
            self.parameter_output_values["keypoints_2d"] = ""
            return

        try:
            joints = json.loads(joints_json)
        except json.JSONDecodeError as e:
            logger.error(f"PoseToControlNet: Invalid JSON: {e}")
            self.parameter_output_values["openpose_json"] = ""
            self.parameter_output_values["keypoints_2d"] = ""
            return

        # Project 3D to 2D based on view
        points_2d = []
        for name in KEYPOINT_ORDER:
            pos = joints.get(name)
            if pos is None or not isinstance(pos, list) or len(pos) < 3:
                points_2d.append(None)
                continue

            x3d, y3d, z3d = pos[0], pos[1], pos[2]

            if view == "side":
                # Side view: Z → X, Y → Y
                px, py = z3d, y3d
            elif view == "top":
                # Top view: X → X, Z → Y
                px, py = x3d, z3d
            else:
                # Front view: X → X, Y → Y
                px, py = x3d, y3d

            points_2d.append([px, py])

        if not any(p is not None for p in points_2d):
            self.parameter_output_values["openpose_json"] = ""
            self.parameter_output_values["keypoints_2d"] = ""
            return

        # Find bounding box of valid points
        valid = [p for p in points_2d if p is not None]
        min_x = min(p[0] for p in valid)
        max_x = max(p[0] for p in valid)
        min_y = min(p[1] for p in valid)
        max_y = max(p[1] for p in valid)

        # Add padding
        range_x = max_x - min_x or 1
        range_y = max_y - min_y or 1
        pad = 0.1
        min_x -= range_x * pad
        max_x += range_x * pad
        min_y -= range_y * pad
        max_y += range_y * pad
        range_x = max_x - min_x
        range_y = max_y - min_y

        # Maintain aspect ratio
        aspect = img_w / img_h
        data_aspect = range_x / range_y
        if data_aspect > aspect:
            # Data is wider: add vertical padding
            new_range_y = range_x / aspect
            center_y = (min_y + max_y) / 2
            min_y = center_y - new_range_y / 2
            range_y = new_range_y
        else:
            # Data is taller: add horizontal padding
            new_range_x = range_y * aspect
            center_x = (min_x + max_x) / 2
            min_x = center_x - new_range_x / 2
            range_x = new_range_x

        # Normalize to image coordinates
        keypoints = []
        for p in points_2d:
            if p is None:
                keypoints.append([0, 0, 0])  # confidence = 0
            else:
                nx = (p[0] - min_x) / range_x * img_w
                # Flip Y (screen coordinates: Y increases downward)
                ny = (1.0 - (p[1] - min_y) / range_y) * img_h
                keypoints.append([round(nx, 1), round(ny, 1), 1.0])

        # Standard OpenPose JSON format
        openpose_data = {
            "people": [
                {
                    "pose_keypoints_2d": [v for kp in keypoints for v in kp],
                }
            ],
            "canvas_width": img_w,
            "canvas_height": img_h,
        }

        self.parameter_output_values["openpose_json"] = json.dumps(openpose_data, indent=2)
        self.parameter_output_values["keypoints_2d"] = json.dumps(keypoints, indent=2)

        logger.info(f"PoseToControlNet: Projected {len(keypoints)} keypoints to {img_w}x{img_h} ({view} view)")
