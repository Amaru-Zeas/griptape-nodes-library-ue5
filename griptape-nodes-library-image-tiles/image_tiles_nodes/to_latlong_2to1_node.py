from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageFilter
from griptape.artifacts import ImageArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.options import Options

from seam_blend_360_node import _read_image_bytes


def _resize_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    scale = max(target_w / float(img.width), target_h / float(img.height))
    w = max(1, int(round(img.width * scale)))
    h = max(1, int(round(img.height * scale)))
    resized = img.resize((w, h), Image.Resampling.LANCZOS)
    left = max(0, (w - target_w) // 2)
    top = max(0, (h - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _resize_contain(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    scale = min(target_w / float(img.width), target_h / float(img.height))
    w = max(1, int(round(img.width * scale)))
    h = max(1, int(round(img.height * scale)))
    return img.resize((w, h), Image.Resampling.LANCZOS)


class ToLatLong2to1Node(DataNode):
    """Convert any image into a 2:1 (equirectangular-friendly) canvas."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "ImageTiles",
            "description": "Convert regular image to 2:1 canvas for latlong workflows.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str", "dict"],
                type="ImageArtifact",
                tooltip="Input image to convert to 2:1 canvas.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_width",
                input_types=["int"],
                type="int",
                default_value=4096,
                tooltip="Output width. Height is always width/2.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="fit_mode",
                input_types=["str"],
                type="str",
                default_value="pad_blur",
                traits={Options(choices=["pad_blur", "pad_black", "crop", "stretch"])},
                tooltip="How to convert to 2:1. pad_blur is usually best.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="background_blur",
                input_types=["int"],
                type="int",
                default_value=32,
                tooltip="Blur amount for pad_blur mode.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="2:1 converted image.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="width",
                output_type="int",
                tooltip="Output image width.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="height",
                output_type="int",
                tooltip="Output image height.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="aspect_ratio",
                output_type="float",
                tooltip="Output width/height ratio (should be 2.0).",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        image_bytes = _read_image_bytes(self.parameter_values.get("image"))
        src = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        output_width = int(self.parameter_values.get("output_width") or 4096)
        output_width = max(512, output_width)
        output_height = max(1, output_width // 2)

        fit_mode = str(self.parameter_values.get("fit_mode") or "pad_blur").strip().lower()
        blur_amount = max(0, int(self.parameter_values.get("background_blur") or 0))

        if fit_mode == "stretch":
            out = src.resize((output_width, output_height), Image.Resampling.LANCZOS)
        elif fit_mode == "crop":
            out = _resize_cover(src, output_width, output_height)
        else:
            fg = _resize_contain(src, output_width, output_height)
            if fit_mode == "pad_blur":
                bg = _resize_cover(src, output_width, output_height)
                if blur_amount > 0:
                    bg = bg.filter(ImageFilter.GaussianBlur(radius=blur_amount))
            else:
                bg = Image.new("RGB", (output_width, output_height), (0, 0, 0))
            left = (output_width - fg.width) // 2
            top = (output_height - fg.height) // 2
            bg.paste(fg, (left, top))
            out = bg

        out_buf = io.BytesIO()
        out.save(out_buf, format="PNG")
        out_bytes = out_buf.getvalue()

        artifact = ImageArtifact(
            value=out_bytes,
            width=out.width,
            height=out.height,
            format="png",
            name=f"{self.name}_latlong_2to1.png",
        )

        self.parameter_output_values["output_image"] = artifact
        self.parameter_output_values["width"] = out.width
        self.parameter_output_values["height"] = out.height
        self.parameter_output_values["aspect_ratio"] = float(out.width) / max(1.0, float(out.height))
