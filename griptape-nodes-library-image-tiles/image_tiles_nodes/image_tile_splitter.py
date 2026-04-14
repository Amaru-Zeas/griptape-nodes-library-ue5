"""Image Tile Splitter node."""

from __future__ import annotations

import base64
import io
import json
import os
import time
from math import ceil
from pathlib import Path
from typing import Any

from PIL import Image
from griptape.artifacts import ImageArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


def _decode_data_url(data_url: str) -> bytes:
    if not isinstance(data_url, str) or "," not in data_url:
        msg = "Invalid data URL image input."
        raise ValueError(msg)
    _, b64_data = data_url.split(",", 1)
    return base64.b64decode(b64_data)


def _candidate_paths(raw_path: str) -> list[Path]:
    text = str(raw_path or "").strip()
    if not text:
        return []

    normalized = text.replace("\\", "/")
    candidates: list[Path] = []

    # Direct path first.
    candidates.append(Path(text))

    # Resolve Griptape-style virtual input token: "{inputs}/...".
    if normalized.startswith("{inputs}/"):
        suffix = normalized[len("{inputs}/") :]
        env_dirs = [
            os.environ.get("GTN_INPUTS_DIR", ""),
            os.environ.get("GRIPTAPE_INPUTS_DIR", ""),
            os.environ.get("INPUTS_DIR", ""),
        ]
        for env_dir in env_dirs:
            if env_dir:
                candidates.append(Path(env_dir) / suffix)
        # Common default Griptape location on local installs.
        candidates.append(Path.home() / "GriptapeNodes" / "inputs" / suffix)
        candidates.append(Path.cwd() / "inputs" / suffix)

    return candidates


def _read_image_bytes(value: Any) -> bytes:
    if value is None:
        msg = "No image input provided."
        raise ValueError(msg)

    if isinstance(value, bytes):
        return value

    if isinstance(value, str):
        if value.startswith("data:"):
            return _decode_data_url(value)

        attempted: list[str] = []
        for path in _candidate_paths(value):
            try:
                attempted.append(str(path))
                if path.exists() and path.is_file():
                    return path.read_bytes()
            except Exception:
                continue

        attempted_text = "; ".join(attempted) if attempted else "<none>"
        msg = (
            "String image input is not a valid data URL or local file path: "
            f"{value}. Attempted: {attempted_text}"
        )
        raise ValueError(msg)

    if isinstance(value, dict):
        for key in ("value", "image", "image_data", "image_data_url", "url", "path"):
            candidate = value.get(key)
            if candidate is not None:
                return _read_image_bytes(candidate)
        msg = "Dict image input did not contain a supported image field."
        raise ValueError(msg)

    raw_value = getattr(value, "value", None)
    if raw_value is not None:
        return _read_image_bytes(raw_value)

    raw_b64 = getattr(value, "base64", None)
    if isinstance(raw_b64, str) and raw_b64:
        if raw_b64.startswith("data:"):
            return _decode_data_url(raw_b64)
        return base64.b64decode(raw_b64)

    msg = f"Unsupported image input type: {type(value).__name__}"
    raise ValueError(msg)


def _default_tiles_root() -> Path:
    configured = os.environ.get("GTN_IMAGE_TILES_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path.home() / "GriptapeNodes" / "io" / "image_tiles"


class ImageTileSplitterNode(DataNode):
    """Split an image into square tiles and emit JSON metadata."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "ImageTiles",
            "description": "Split an image into square PNG tiles and output a merge manifest.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str", "dict"],
                type="ImageArtifact",
                tooltip="Image to split (artifact, path, data URL, or compatible dict).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="tile_size",
                input_types=["int"],
                type="int",
                default_value=512,
                tooltip="Square tile size in pixels.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="pad_to_fit",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Pad image to full tile grid; merged output still crops to original size.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="tiles_manifest_json",
                output_type="str",
                tooltip="Small JSON payload pointing to manifest_path on disk.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="manifest_path",
                output_type="str",
                tooltip="Path to the full manifest JSON file on disk.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="tiles_folder",
                output_type="str",
                tooltip="Directory where this run's tile PNG files were saved.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="tile_count",
                output_type="int",
                tooltip="Total number of generated tiles.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="rows",
                output_type="int",
                tooltip="Number of tile rows.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="columns",
                output_type="int",
                tooltip="Number of tile columns.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        image_value = self.parameter_values.get("image")
        tile_size = int(self.parameter_values.get("tile_size") or 512)
        pad_to_fit = bool(self.parameter_values.get("pad_to_fit", True))

        if tile_size <= 0:
            msg = "tile_size must be greater than 0."
            raise ValueError(msg)

        image_bytes = _read_image_bytes(image_value)
        source = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        original_width, original_height = source.size

        columns = ceil(original_width / tile_size)
        rows = ceil(original_height / tile_size)

        if pad_to_fit:
            padded_width = columns * tile_size
            padded_height = rows * tile_size
            padded = Image.new("RGBA", (padded_width, padded_height), (0, 0, 0, 0))
            padded.paste(source, (0, 0))
            working = padded
        else:
            working = source

        working_width, working_height = working.size
        tiles: list[dict[str, Any]] = []
        index = 0
        run_dir = _default_tiles_root() / f"{self.name}_{int(time.time() * 1000)}"
        run_dir.mkdir(parents=True, exist_ok=True)

        for row in range(rows):
            for col in range(columns):
                x = col * tile_size
                y = row * tile_size
                right = min(x + tile_size, working_width)
                bottom = min(y + tile_size, working_height)

                if right <= x or bottom <= y:
                    continue

                tile = working.crop((x, y, right, bottom))
                tile_name = f"tile_r{row:04d}_c{col:04d}.png"
                tile_path = run_dir / tile_name
                tile.save(tile_path, format="PNG")

                tiles.append(
                    {
                        "index": index,
                        "row": row,
                        "col": col,
                        "x": x,
                        "y": y,
                        "width": right - x,
                        "height": bottom - y,
                        "tile_path": str(tile_path),
                    }
                )
                index += 1

        manifest = {
            "version": "1.0",
            "tile_size": tile_size,
            "pad_to_fit": pad_to_fit,
            "original_width": original_width,
            "original_height": original_height,
            "rows": rows,
            "columns": columns,
            "tile_count": len(tiles),
            "tiles_folder": str(run_dir),
            "tiles": tiles,
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")

        self.parameter_output_values["tiles_manifest_json"] = json.dumps(
            {"manifest_path": str(manifest_path)},
            ensure_ascii=True,
        )
        self.parameter_output_values["manifest_path"] = str(manifest_path)
        self.parameter_output_values["tiles_folder"] = str(run_dir)
        self.parameter_output_values["tile_count"] = len(tiles)
        self.parameter_output_values["rows"] = rows
        self.parameter_output_values["columns"] = columns
