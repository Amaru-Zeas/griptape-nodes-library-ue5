from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class Equirect360DimensionsNode(DataNode):
    """Compute valid 2:1 equirectangular dimensions and latent sizes."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "DiT360",
            "description": "Normalize panorama dimensions to valid 2:1 size and latent dimensions.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                default_value=2048,
                tooltip="Target panorama width.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="alignment",
                input_types=["int"],
                type="int",
                default_value=16,
                tooltip="Round width to nearest lower multiple of this value.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="vae_scale_factor",
                input_types=["int"],
                type="int",
                default_value=8,
                tooltip="Latent downscale factor (8 for FLUX VAE).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="resolved_width",
                output_type="int",
                tooltip="Aligned panorama width.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="resolved_height",
                output_type="int",
                tooltip="2:1 panorama height derived from width.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="latent_width",
                output_type="int",
                tooltip="Latent-space width.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="latent_height",
                output_type="int",
                tooltip="Latent-space height.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        width = int(self.parameter_values.get("width") or 2048)
        alignment = max(1, int(self.parameter_values.get("alignment") or 16))
        vae_scale = max(1, int(self.parameter_values.get("vae_scale_factor") or 8))

        width = max(alignment, (width // alignment) * alignment)
        height = max(1, width // 2)

        latent_width = max(1, width // vae_scale)
        latent_height = max(1, height // vae_scale)

        self.parameter_output_values["resolved_width"] = width
        self.parameter_output_values["resolved_height"] = height
        self.parameter_output_values["latent_width"] = latent_width
        self.parameter_output_values["latent_height"] = latent_height

