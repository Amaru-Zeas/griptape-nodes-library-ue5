from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class DiT360FluxDevPresetNode(DataNode):
    """Emit FLUX.1-dev + DiT360 LoRA defaults for GTN workflows."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "DiT360",
            "description": "Preset outputs for FLUX.1-dev + DiT360 LoRA panorama generation.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="flux_model_id",
                output_type="str",
                default_value="black-forest-labs/FLUX.1-dev",
                tooltip="Recommended FLUX base model id.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="dit360_lora_id",
                output_type="str",
                default_value="Insta360-Research/DiT360-Panorama-Image-Generation",
                tooltip="Recommended DiT360 LoRA repo id.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="dit360_lora_filename",
                output_type="str",
                default_value="dit360.safetensors",
                tooltip="Suggested DiT360 LoRA filename.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_width",
                output_type="int",
                default_value=2048,
                tooltip="Recommended panorama width.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_height",
                output_type="int",
                default_value=1024,
                tooltip="Recommended panorama height (2:1).",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_steps",
                output_type="int",
                default_value=20,
                tooltip="Recommended generation steps starting point.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_guidance",
                output_type="float",
                default_value=3.5,
                tooltip="Recommended guidance scale starting point.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt_hint",
                output_type="str",
                default_value="Describe the full 360 environment around the camera viewpoint.",
                tooltip="Prompting reminder for 360 panorama quality.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        self.parameter_output_values["flux_model_id"] = "black-forest-labs/FLUX.1-dev"
        self.parameter_output_values["dit360_lora_id"] = "Insta360-Research/DiT360-Panorama-Image-Generation"
        self.parameter_output_values["dit360_lora_filename"] = "dit360.safetensors"
        self.parameter_output_values["recommended_width"] = 2048
        self.parameter_output_values["recommended_height"] = 1024
        self.parameter_output_values["recommended_steps"] = 20
        self.parameter_output_values["recommended_guidance"] = 3.5
        self.parameter_output_values["prompt_hint"] = "Describe the full 360 environment around the camera viewpoint."

