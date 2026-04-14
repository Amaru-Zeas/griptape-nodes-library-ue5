"""Video Frame Editor node for frame-accurate scrubbing and extraction."""

import base64
import io
import logging
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image
from griptape.artifacts import ImageArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget

logger = logging.getLogger(__name__)
NODE_VERSION = "v2.5.0-cache10"
DEFAULT_STATICFILES_DIR = Path(r"C:\Users\AI PC\GriptapeNodes\staticfiles")


class VideoFrameEditorNodeV3(DataNode):
    """Video utility node driven by a custom widget.

    The widget handles local video loading in-browser and returns frame metadata
    plus extracted PNG data URLs back to the node.
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "VideoTools",
            "description": "Import video, move frame-by-frame, and extract current frame as image.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        self.set_initial_node_size(width=980, height=880)

        self.add_parameter(
            Parameter(
                name="video_editor",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={
                    "fps": 30,
                    "frame_index": 0,
                    "frame_time_seconds": 0.0,
                    "total_frames": 0,
                    "video_name": "",
                    "frame_image_data": "",
                    "extract_nonce": "",
                },
                tooltip="Video frame editor widget for frame-accurate stepping and extraction.",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Widget(name="VideoFrameEditorWidgetForceV4", library="GTN Video Edit Tools")},
            )
        )

        self.add_parameter(
            Parameter(
                name="extracted_frame",
                output_type="ImageArtifact",
                tooltip="Extracted frame as ImageArtifact connector output.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="extracted_frame_path",
                output_type="str",
                tooltip="Absolute path where the extracted frame was saved.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="extracted_frame_url",
                output_type="str",
                tooltip="Staticfiles URL path for the extracted frame.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _image_artifact_from_data_url(self, data_url: str) -> tuple[ImageArtifact | None, str, str]:
        if not isinstance(data_url, str) or not data_url.startswith("data:"):
            return None, "", ""

        try:
            header, b64_data = data_url.split(",", 1)
            raw = base64.b64decode(b64_data)
        except Exception:
            return None, "", ""

        mime = header.split(";", 1)[0].replace("data:", "").strip().lower()
        fmt_map = {"image/png": "png", "image/jpeg": "jpeg", "image/jpg": "jpeg", "image/webp": "webp"}
        fmt = fmt_map.get(mime, "png")

        try:
            img = Image.open(io.BytesIO(raw))
            width, height = img.size
        except Exception:
            return None, "", ""

        file_name = f"gtn_video_frame_{int(time.time() * 1000)}.{fmt}"
        static_dir = Path(os.environ.get("GTN_STATICFILES_DIR", str(DEFAULT_STATICFILES_DIR)))
        try:
            static_dir.mkdir(parents=True, exist_ok=True)
            out_path = static_dir / file_name
            with out_path.open("wb") as f:
                f.write(raw)
            stored_bytes = out_path.read_bytes()
            static_path = str(out_path)
            static_url = f"/staticfiles/{file_name}"
        except Exception:
            # Fall back to in-memory bytes if staticfiles write fails.
            stored_bytes = raw
            static_path = ""
            static_url = ""

        if fmt in {"png", "jpeg", "webp"}:
            return ImageArtifact(value=stored_bytes, width=width, height=height, format=fmt, name=file_name), static_path, static_url

        # Fallback re-encode if mime was non-standard.
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        png_name = f"gtn_video_frame_{int(time.time() * 1000)}.png"
        png_bytes = buffer.getvalue()
        try:
            static_dir = Path(os.environ.get("GTN_STATICFILES_DIR", str(DEFAULT_STATICFILES_DIR)))
            static_dir.mkdir(parents=True, exist_ok=True)
            out_path = static_dir / png_name
            with out_path.open("wb") as f:
                f.write(png_bytes)
            png_bytes = out_path.read_bytes()
            static_path = str(out_path)
            static_url = f"/staticfiles/{png_name}"
        except Exception:
            static_path = ""
            static_url = ""
        return ImageArtifact(value=png_bytes, width=width, height=height, format="png", name=png_name), static_path, static_url

    def process(self) -> None:
        data = self.parameter_values.get("video_editor", {})
        if not isinstance(data, dict):
            data = {}

        frame_image_data = data.get("frame_image_data", "")

        if not isinstance(frame_image_data, str):
            frame_image_data = ""

        artifact, static_path, static_url = self._image_artifact_from_data_url(frame_image_data) if frame_image_data else (None, "", "")
        self.parameter_output_values["extracted_frame"] = artifact
        self.parameter_output_values["extracted_frame_path"] = static_path
        self.parameter_output_values["extracted_frame_url"] = static_url

        logger.info(
            "VideoFrameEditorNodeV3(%s): extracted=%s path=%s",
            NODE_VERSION,
            "yes" if artifact is not None else "no",
            static_path or "<none>",
        )


class VideoFrameEditorNodeV2(VideoFrameEditorNodeV3):
    """Backwards-compatible alias for older class name references."""


class VideoFrameEditorNode(VideoFrameEditorNodeV3):
    """Backwards-compatible alias for older class name references."""
