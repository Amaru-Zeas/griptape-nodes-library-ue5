"""Image Tile Merger node."""

from __future__ import annotations

import base64
import io
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter
from griptape.artifacts import ImageUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


def _tile_image_from_data_url(data_url: str) -> Image.Image:
    if not isinstance(data_url, str) or not data_url.startswith("data:") or "," not in data_url:
        msg = "Each tile image_data must be a valid data URL."
        raise ValueError(msg)
    _, b64_data = data_url.split(",", 1)
    raw = base64.b64decode(b64_data)
    return Image.open(io.BytesIO(raw)).convert("RGBA")


def _tile_image_from_entry(tile: dict[str, Any]) -> Image.Image:
    tile_path = tile.get("tile_path")
    if isinstance(tile_path, str) and tile_path.strip():
        path = Path(tile_path)
        if path.exists() and path.is_file():
            return Image.open(path).convert("RGBA")

    tile_image_data = tile.get("image_data", "")
    return _tile_image_from_data_url(tile_image_data)


def _tile_image_from_entry_with_override(tile: dict[str, Any], override_folder: str) -> Image.Image:
    folder = (override_folder or "").strip()
    if folder:
        source_path = tile.get("tile_path")
        if isinstance(source_path, str) and source_path.strip():
            candidate = Path(folder) / Path(source_path).name
            if candidate.exists() and candidate.is_file():
                return Image.open(candidate).convert("RGBA")
    return _tile_image_from_entry(tile)


def _parse_manifest(value: Any) -> dict[str, Any]:
    if value is None:
        msg = "tiles_manifest_json is empty."
        raise ValueError(msg)

    wrapped_value = getattr(value, "value", None)
    if wrapped_value is not None:
        return _parse_manifest(wrapped_value)

    wrapped_path = getattr(value, "path", None)
    if isinstance(wrapped_path, str) and wrapped_path.strip():
        return _parse_manifest(wrapped_path)

    if isinstance(value, bytes):
        return _parse_manifest(value.decode("utf-8", errors="replace"))

    if isinstance(value, dict):
        if "value" in value and value.get("value") is not None:
            return _parse_manifest(value.get("value"))
        manifest_path = value.get("manifest_path")
        if isinstance(manifest_path, str) and manifest_path.strip():
            path = Path(manifest_path)
            if path.exists() and path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        return value
    if isinstance(value, str):
        raw = value.strip()
        path = Path(raw)
        if path.exists() and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            msg = "Manifest JSON must decode to an object."
            raise ValueError(msg)
        manifest_path = parsed.get("manifest_path")
        if isinstance(manifest_path, str) and manifest_path.strip():
            nested_path = Path(manifest_path)
            if nested_path.exists() and nested_path.is_file():
                return json.loads(nested_path.read_text(encoding="utf-8"))
        return parsed
    msg = f"tiles_manifest_json must be a JSON string or dict. Received: {type(value).__name__}"
    raise ValueError(msg)


def _default_merged_root() -> Path:
    configured = os.environ.get("GTN_IMAGE_TILES_DIR", "").strip()
    if configured:
        return Path(configured) / "merged"
    return Path.home() / "GriptapeNodes" / "io" / "image_tiles" / "merged"


def _seam_mask(size: tuple[int, int], feather: int, vertical: bool) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    if feather <= 0:
        return mask

    if vertical:
        center = (width - 1) / 2.0
        for x in range(width):
            distance = abs(x - center)
            value = int(max(0.0, 1.0 - (distance / float(feather))) * 255.0)
            if value <= 0:
                continue
            mask.paste(value, (x, 0, x + 1, height))
    else:
        center = (height - 1) / 2.0
        for y in range(height):
            distance = abs(y - center)
            value = int(max(0.0, 1.0 - (distance / float(feather))) * 255.0)
            if value <= 0:
                continue
            mask.paste(value, (0, y, width, y + 1))
    return mask


def _soften_tile_seams(image: Image.Image, vertical_seams: list[int], horizontal_seams: list[int], feather: int) -> Image.Image:
    if feather <= 0:
        return image

    out = image.copy()
    blur_radius = max(1, int(round(feather / 2)))

    for seam_x in vertical_seams:
        left = max(0, seam_x - feather)
        right = min(out.width, seam_x + feather)
        if right - left < 2:
            continue
        band = out.crop((left, 0, right, out.height))
        softened = band.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        mask = _seam_mask((band.width, band.height), feather=feather, vertical=True)
        blended = Image.composite(softened, band, mask)
        out.paste(blended, (left, 0))

    for seam_y in horizontal_seams:
        top = max(0, seam_y - feather)
        bottom = min(out.height, seam_y + feather)
        if bottom - top < 2:
            continue
        band = out.crop((0, top, out.width, bottom))
        softened = band.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        mask = _seam_mask((band.width, band.height), feather=feather, vertical=False)
        blended = Image.composite(softened, band, mask)
        out.paste(blended, (0, top))

    return out


class ImageTileMergerNode(DataNode):
    """Merge square image tiles from a splitter manifest."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "ImageTiles",
            "description": "Merge tile manifest back into one image.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="tiles_manifest_json",
                input_types=["str", "dict"],
                type="str",
                tooltip="Manifest JSON output from Image Tile Splitter.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="tiles_folder_override",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional folder containing replacement tile files with same tile names.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="seam_fix_px",
                input_types=["int"],
                type="int",
                default_value=12,
                tooltip="Seam softening width in pixels (0 disables seam fixing).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="merged_image",
                output_type="ImageUrlArtifact",
                tooltip="Merged output image path artifact.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="merged_image_path",
                output_type="str",
                tooltip="Absolute path to merged PNG on disk.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="merged_width",
                output_type="int",
                tooltip="Merged image width in pixels.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="merged_height",
                output_type="int",
                tooltip="Merged image height in pixels.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        manifest_value = self.parameter_values.get("tiles_manifest_json")
        tiles_folder_override = str(self.parameter_values.get("tiles_folder_override") or "").strip()
        seam_fix_px = int(self.parameter_values.get("seam_fix_px") or 0)
        manifest = _parse_manifest(manifest_value)

        tiles_raw = manifest.get("tiles", [])
        if not isinstance(tiles_raw, list) or not tiles_raw:
            msg = "Manifest does not contain any tiles."
            raise ValueError(msg)

        prepared_tiles: list[dict[str, Any]] = []
        scale_x_values: list[float] = []
        scale_y_values: list[float] = []
        max_row = -1
        max_col = -1

        for tile in tiles_raw:
            if not isinstance(tile, dict):
                msg = "Each tile entry must be an object."
                raise ValueError(msg)
            row = int(tile.get("row", 0))
            col = int(tile.get("col", 0))
            x = int(tile.get("x", 0))
            y = int(tile.get("y", 0))
            width = int(tile.get("width", 0))
            height = int(tile.get("height", 0))
            tile_image = _tile_image_from_entry_with_override(tile, tiles_folder_override)

            if width > 0:
                scale_x_values.append(tile_image.width / width)
            if height > 0:
                scale_y_values.append(tile_image.height / height)

            max_row = max(max_row, row)
            max_col = max(max_col, col)

            prepared_tiles.append(
                {
                    "row": row,
                    "col": col,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "image": tile_image,
                }
            )

        scale_x = statistics.median(scale_x_values) if scale_x_values else 1.0
        scale_y = statistics.median(scale_y_values) if scale_y_values else 1.0
        if scale_x <= 0:
            scale_x = 1.0
        if scale_y <= 0:
            scale_y = 1.0

        row_count = int(manifest.get("rows") or (max_row + 1))
        col_count = int(manifest.get("columns") or (max_col + 1))
        row_count = max(1, row_count)
        col_count = max(1, col_count)

        col_widths = [0] * col_count
        row_heights = [0] * row_count
        for tile in prepared_tiles:
            col = int(tile["col"])
            row = int(tile["row"])
            expected_w = int(round(max(1, int(tile["width"])) * scale_x))
            expected_h = int(round(max(1, int(tile["height"])) * scale_y))
            tile["expected_w"] = max(1, expected_w)
            tile["expected_h"] = max(1, expected_h)
            if 0 <= col < col_count:
                col_widths[col] = max(col_widths[col], int(tile["expected_w"]))
            if 0 <= row < row_count:
                row_heights[row] = max(row_heights[row], int(tile["expected_h"]))

        # Fallback for missing cells in sparse manifests.
        for col in range(col_count):
            if col_widths[col] <= 0:
                col_widths[col] = int(round((manifest.get("tile_size") or 1) * scale_x))
        for row in range(row_count):
            if row_heights[row] <= 0:
                row_heights[row] = int(round((manifest.get("tile_size") or 1) * scale_y))

        col_offsets = [0] * col_count
        row_offsets = [0] * row_count
        for col in range(1, col_count):
            col_offsets[col] = col_offsets[col - 1] + col_widths[col - 1]
        for row in range(1, row_count):
            row_offsets[row] = row_offsets[row - 1] + row_heights[row - 1]

        max_right = 0
        max_bottom = 0
        for tile in prepared_tiles:
            col = int(tile["col"])
            row = int(tile["row"])
            dest_x = col_offsets[col] if 0 <= col < col_count else int(round(tile["x"] * scale_x))
            dest_y = row_offsets[row] if 0 <= row < row_count else int(round(tile["y"] * scale_y))
            target_w = int(tile.get("expected_w", tile["image"].width))
            target_h = int(tile.get("expected_h", tile["image"].height))
            max_right = max(max_right, dest_x + target_w)
            max_bottom = max(max_bottom, dest_y + target_h)

        if max_right <= 0 or max_bottom <= 0:
            msg = "Invalid tile coordinates in manifest."
            raise ValueError(msg)

        canvas = Image.new("RGBA", (max_right, max_bottom), (0, 0, 0, 0))

        for tile in prepared_tiles:
            col = int(tile["col"])
            row = int(tile["row"])
            dest_x = col_offsets[col] if 0 <= col < col_count else int(round(tile["x"] * scale_x))
            dest_y = row_offsets[row] if 0 <= row < row_count else int(round(tile["y"] * scale_y))
            target_w = int(tile.get("expected_w", tile["image"].width))
            target_h = int(tile.get("expected_h", tile["image"].height))
            tile_image = tile["image"]
            if tile_image.width != target_w or tile_image.height != target_h:
                tile_image = tile_image.resize((target_w, target_h), Image.Resampling.LANCZOS)
            canvas.paste(tile_image, (dest_x, dest_y))

        original_width = int(manifest.get("original_width") or canvas.width)
        original_height = int(manifest.get("original_height") or canvas.height)
        original_width = int(round(original_width * scale_x))
        original_height = int(round(original_height * scale_y))
        original_width = max(1, min(original_width, canvas.width))
        original_height = max(1, min(original_height, canvas.height))
        final_image = canvas.crop((0, 0, original_width, original_height))
        vertical_seams = [offset for offset in col_offsets[1:] if 0 < offset < final_image.width]
        horizontal_seams = [offset for offset in row_offsets[1:] if 0 < offset < final_image.height]
        final_image = _soften_tile_seams(final_image, vertical_seams, horizontal_seams, max(0, seam_fix_px))

        merged_root = _default_merged_root()
        merged_root.mkdir(parents=True, exist_ok=True)
        merged_path = merged_root / f"{self.name}_{int(time.time() * 1000)}.png"
        final_image.save(merged_path, format="PNG")

        self.parameter_output_values["merged_image"] = ImageUrlArtifact(value=str(merged_path))
        self.parameter_output_values["merged_image_path"] = str(merged_path)
        self.parameter_output_values["merged_width"] = final_image.width
        self.parameter_output_values["merged_height"] = final_image.height
