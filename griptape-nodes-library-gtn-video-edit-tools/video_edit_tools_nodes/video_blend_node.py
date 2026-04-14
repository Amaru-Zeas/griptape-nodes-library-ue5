"""Simple video blending node with basic blend modes."""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import numpy as np
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)
DEFAULT_FPS = 30.0
VALID_BLEND_MODES = {"normal", "screen", "multiply", "add", "overlay"}


def _to_rgb(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return np.stack([frame, frame, frame], axis=-1)
    if frame.ndim == 3 and frame.shape[2] == 4:
        return frame[:, :, :3]
    return frame


def _resolve_video_value(video_input: Any) -> str:
    if video_input is None:
        return ""
    if isinstance(video_input, dict):
        value = video_input.get("value") or video_input.get("url")
        return value if isinstance(value, str) else ""
    value = getattr(video_input, "value", None)
    if isinstance(value, str):
        return value
    if isinstance(video_input, str):
        return video_input
    return ""


def _blend_frame(base_frame: np.ndarray, top_frame: np.ndarray, blend_mode: str, opacity: float) -> np.ndarray:
    base = base_frame.astype(np.float32) / 255.0
    top = top_frame.astype(np.float32) / 255.0

    if blend_mode == "screen":
        blended = 1.0 - ((1.0 - base) * (1.0 - top))
    elif blend_mode == "multiply":
        blended = base * top
    elif blend_mode == "add":
        blended = np.clip(base + top, 0.0, 1.0)
    elif blend_mode == "overlay":
        blended = np.where(base <= 0.5, 2.0 * base * top, 1.0 - 2.0 * (1.0 - base) * (1.0 - top))
    else:
        blended = top

    mixed = ((1.0 - opacity) * base) + (opacity * blended)
    return np.clip(mixed * 255.0, 0.0, 255.0).astype(np.uint8)


class VideoBlendNode(DataNode):
    """Blend two videos into one output video."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "VideoTools",
            "description": "Blend two videos frame-by-frame and output a single video.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        self.set_initial_node_size(width=500, height=580)

        self.add_parameter(
            Parameter(
                name="base_video",
                input_types=["VideoArtifact", "VideoUrlArtifact", "dict"],
                type="VideoArtifact",
                output_type="VideoUrlArtifact",
                tooltip="Base video layer.",
            )
        )
        self.add_parameter(
            Parameter(
                name="overlay_video",
                input_types=["VideoArtifact", "VideoUrlArtifact", "dict"],
                type="VideoArtifact",
                output_type="VideoUrlArtifact",
                tooltip="Overlay video layer to blend over base.",
            )
        )
        self.add_parameter(
            Parameter(
                name="blend_mode",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="screen",
                tooltip="Blend mode: normal, screen, multiply, add, overlay.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="opacity",
                input_types=["float"],
                type="float",
                output_type="float",
                default_value=1.0,
                tooltip="Blend strength of overlay [0.0 to 1.0].",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Final blended video output.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        base_value = _resolve_video_value(self.parameter_values.get("base_video"))
        overlay_value = _resolve_video_value(self.parameter_values.get("overlay_video"))

        if not base_value or not overlay_value:
            raise ValueError("Both base_video and overlay_video are required.")

        mode_value = self.parameter_values.get("blend_mode")
        blend_mode = str(mode_value).strip().lower() if mode_value else "screen"
        if blend_mode not in VALID_BLEND_MODES:
            blend_mode = "screen"

        opacity_value = self.parameter_values.get("opacity")
        try:
            opacity = float(opacity_value)
        except (TypeError, ValueError):
            opacity = 1.0
        opacity = max(0.0, min(1.0, opacity))

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_dir = Path(tmp_dir)
            base_path = temp_dir / "base.mp4"
            overlay_path = temp_dir / "overlay.mp4"
            base_path.write_bytes(File(base_value).read_bytes())
            overlay_path.write_bytes(File(overlay_value).read_bytes())

            base_reader = imageio.get_reader(str(base_path))
            overlay_reader = imageio.get_reader(str(overlay_path))
            try:
                base_frames = [_to_rgb(np.asarray(frame)) for frame in base_reader]
                overlay_frames = [_to_rgb(np.asarray(frame)) for frame in overlay_reader]
                base_meta = base_reader.get_meta_data()
                overlay_meta = overlay_reader.get_meta_data()
            finally:
                base_reader.close()
                overlay_reader.close()

            frame_count = min(len(base_frames), len(overlay_frames))
            if frame_count == 0:
                raise ValueError("One or both videos contain no readable frames.")

            fps_a = float(base_meta.get("fps", DEFAULT_FPS) or DEFAULT_FPS)
            fps_b = float(overlay_meta.get("fps", DEFAULT_FPS) or DEFAULT_FPS)
            fps = min(fps_a, fps_b) if fps_a > 0 and fps_b > 0 else DEFAULT_FPS

            blended_frames: list[np.ndarray] = []
            for idx in range(frame_count):
                a = base_frames[idx]
                b = overlay_frames[idx]
                target_h = min(a.shape[0], b.shape[0])
                target_w = min(a.shape[1], b.shape[1])
                a = a[:target_h, :target_w]
                b = b[:target_h, :target_w]
                blended_frames.append(_blend_frame(a, b, blend_mode, opacity))

            output_path = temp_dir / f"blended_{uuid.uuid4()}.mp4"
            imageio.mimsave(str(output_path), blended_frames, fps=fps)

            output_name = f"{uuid.uuid4()}.mp4"
            output_url = GriptapeNodes.StaticFilesManager().save_static_file(output_path.read_bytes(), output_name)
            self.parameter_output_values["output_video"] = VideoUrlArtifact(output_url)

        logger.info(
            "VideoBlendNode: mode=%s opacity=%.3f frames=%s output=%s",
            blend_mode,
            opacity,
            frame_count,
            "set",
        )
