from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class LTX23DefaultsNode(DataNode):
    """Emit practical starter defaults for LTX-2.3 workflows."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "LTX23",
            "description": "Starter defaults for LTX-2.3 generation setup.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="recommended_pipeline_module",
                output_type="str",
                default_value="ti2vid_two_stages",
                tooltip="Recommended pipeline module for best quality.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_checkpoint_name",
                output_type="str",
                default_value="ltx-2.3-22b-dev.safetensors",
                tooltip="Suggested full model checkpoint filename.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_distilled_lora_name",
                output_type="str",
                default_value="ltx-2.3-22b-distilled-lora-384.safetensors",
                tooltip="Suggested distilled LoRA filename for two-stage pipelines.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_frames",
                output_type="int",
                default_value=121,
                tooltip="Good starting frame count (8k+1 compatible).",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_steps",
                output_type="int",
                default_value=40,
                tooltip="Good starting denoising step count for two-stage generation.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="recommended_cfg",
                output_type="float",
                default_value=3.0,
                tooltip="Good starting CFG scale for video guider.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        self.parameter_output_values["recommended_pipeline_module"] = "ti2vid_two_stages"
        self.parameter_output_values["recommended_checkpoint_name"] = "ltx-2.3-22b-dev.safetensors"
        self.parameter_output_values["recommended_distilled_lora_name"] = "ltx-2.3-22b-distilled-lora-384.safetensors"
        self.parameter_output_values["recommended_frames"] = 121
        self.parameter_output_values["recommended_steps"] = 40
        self.parameter_output_values["recommended_cfg"] = 3.0
