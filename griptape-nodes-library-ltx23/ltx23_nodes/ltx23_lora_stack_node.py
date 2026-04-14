from __future__ import annotations

import json
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class LTX23LoraStackNode(DataNode):
    """Build a serialized LoRA stack for LTX generation nodes."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "LTX23",
            "description": "Build JSON LoRA payload from up to 4 path/strength slots.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        for idx in range(1, 5):
            self.add_parameter(
                Parameter(
                    name=f"lora_{idx}_path",
                    input_types=["str"],
                    type="str",
                    default_value="",
                    tooltip=f"Optional path for LoRA #{idx}.",
                )
            )
            self.add_parameter(
                Parameter(
                    name=f"lora_{idx}_strength",
                    input_types=["float"],
                    type="float",
                    default_value=1.0,
                    tooltip=f"Strength for LoRA #{idx}.",
                )
            )

        self.add_parameter(
            Parameter(
                name="lora_stack_json",
                output_type="str",
                tooltip="JSON list used by LTX-2.3 Generate node.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="active_lora_count",
                output_type="int",
                tooltip="How many non-empty LoRA slots were included.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        loras: list[dict[str, Any]] = []
        for idx in range(1, 5):
            path = str(self.get_parameter_value(f"lora_{idx}_path") or "").strip()
            if not path:
                continue
            strength = float(self.get_parameter_value(f"lora_{idx}_strength") or 1.0)
            loras.append({"path": path, "strength": strength})

        self.parameter_output_values["lora_stack_json"] = json.dumps(loras)
        self.parameter_output_values["active_lora_count"] = len(loras)
