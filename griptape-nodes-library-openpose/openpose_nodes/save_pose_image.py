"""Save Pose Image – Decode a captured base64 image and save to file."""

import base64
import logging
import os
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger(__name__)


class SavePoseImage(ControlNode):
    """Save a captured pose image (or depth/normal map) to a PNG file.

    Takes a base64 data URL from the Pose Editor's capture output and saves it
    as a PNG file at the specified path. Works with pose images, depth maps,
    and normal maps.
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "PoseTools",
            "description": "Save a captured pose image, depth map, or normal map to a PNG file",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        # Input: base64 image data URL
        self.add_parameter(
            Parameter(
                name="image_data",
                input_types=["str"],
                type="str",
                tooltip="Base64 PNG data URL from the Pose Editor capture (e.g. 'data:image/png;base64,...')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Connect to captured_image, depth_map, or normal_map output"},
            )
        )

        # Input: file path
        self.add_parameter(
            Parameter(
                name="file_path",
                input_types=["str"],
                type="str",
                default_value="pose_output.png",
                tooltip="File path where the image will be saved (PNG format)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Output: saved file path
        self.add_parameter(
            Parameter(
                name="saved_path",
                output_type="str",
                tooltip="Absolute path of the saved image file",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Output: success flag
        self.add_parameter(
            Parameter(
                name="success",
                output_type="bool",
                tooltip="Whether the image was saved successfully",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        image_data = self.parameter_values.get("image_data", "")
        file_path = self.parameter_values.get("file_path", "pose_output.png")

        if not image_data:
            logger.warning("SavePoseImage: No image data provided. Capture an image first using the 📷 button in the editor.")
            self.parameter_output_values["saved_path"] = ""
            self.parameter_output_values["success"] = False
            return

        try:
            # Strip data URL prefix if present
            if "base64," in image_data:
                image_data = image_data.split("base64,")[1]

            # Decode base64
            img_bytes = base64.b64decode(image_data)

            # Ensure directory exists
            dir_path = os.path.dirname(os.path.abspath(file_path))
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)

            # Write file
            abs_path = os.path.abspath(file_path)
            with open(abs_path, "wb") as f:
                f.write(img_bytes)

            self.parameter_output_values["saved_path"] = abs_path
            self.parameter_output_values["success"] = True
            logger.info(f"SavePoseImage: Saved {len(img_bytes)} bytes to {abs_path}")

        except Exception as e:
            logger.error(f"SavePoseImage: Failed to save image: {e}")
            self.parameter_output_values["saved_path"] = ""
            self.parameter_output_values["success"] = False
