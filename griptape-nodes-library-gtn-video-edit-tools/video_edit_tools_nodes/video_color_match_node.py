"""Video color-match node using color-matcher algorithms frame-by-frame."""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import numpy as np
from color_matcher import ColorMatcher  # type: ignore[reportMissingImports]
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)
DEFAULT_FPS = 30.0
COLOR_MATCH_METHODS = ["mkl", "hm", "reinhard", "mvgd", "hm-mvgd-hm", "hm-mkl-hm"]
MIN_STRENGTH = 0.0
MAX_STRENGTH = 10.0
DEFAULT_STRENGTH = 1.0


def _to_rgb(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return np.stack([frame, frame, frame], axis=-1)
    if frame.ndim == 3 and frame.shape[2] >= 3:
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


def _frame_color_match(
    color_matcher: ColorMatcher, target_frame: np.ndarray, reference_frame: np.ndarray, method: str, strength: float
) -> np.ndarray:
    target_rgb = _to_rgb(target_frame).astype(np.float32) / 255.0
    reference_rgb = _to_rgb(reference_frame).astype(np.float32) / 255.0

    if not target_rgb.flags["C_CONTIGUOUS"]:
        target_rgb = np.ascontiguousarray(target_rgb)
    if not reference_rgb.flags["C_CONTIGUOUS"]:
        reference_rgb = np.ascontiguousarray(reference_rgb)

    matched = color_matcher.transfer(src=target_rgb, ref=reference_rgb, method=method)
    if strength != 1.0:
        matched = target_rgb + strength * (matched - target_rgb)
    matched = np.clip(matched, 0.0, 1.0)
    return (matched * 255.0).astype(np.uint8)


class VideoColorMatchNode(DataNode):
    """Transfer color characteristics from one video to another."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "VideoTools",
            "description": "Transfer color characteristics from reference video to target video.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        self.set_initial_node_size(width=560, height=700)

        self.add_parameter(
            Parameter(
                name="reference_video",
                input_types=["VideoArtifact", "VideoUrlArtifact", "dict"],
                type="VideoArtifact",
                output_type="VideoUrlArtifact",
                tooltip="Reference video (source of color palette).",
            )
        )
        self.add_parameter(
            Parameter(
                name="target_video",
                input_types=["VideoArtifact", "VideoUrlArtifact", "dict"],
                type="VideoArtifact",
                output_type="VideoUrlArtifact",
                tooltip="Target video to receive color transfer.",
            )
        )
        self.add_parameter(
            Parameter(
                name="method",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="mkl",
                tooltip="Color transfer method: mkl, hm, reinhard, mvgd, hm-mvgd-hm, hm-mkl-hm.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="strength",
                input_types=["float"],
                type="float",
                output_type="float",
                default_value=DEFAULT_STRENGTH,
                tooltip="Blend strength [0.0 to 10.0]. 1.0 is full transfer.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Color-matched video output.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        reference_value = _resolve_video_value(self.parameter_values.get("reference_video"))
        target_value = _resolve_video_value(self.parameter_values.get("target_video"))
        if not reference_value or not target_value:
            raise ValueError("Both reference_video and target_video are required.")

        method_value = self.parameter_values.get("method")
        method = str(method_value).strip().lower() if method_value else "mkl"
        if method not in COLOR_MATCH_METHODS:
            method = "mkl"

        strength_value = self.parameter_values.get("strength")
        try:
            strength = float(strength_value)
        except (TypeError, ValueError):
            strength = DEFAULT_STRENGTH
        strength = max(MIN_STRENGTH, min(MAX_STRENGTH, strength))

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_dir = Path(tmp_dir)
            reference_path = temp_dir / "reference.mp4"
            target_path = temp_dir / "target.mp4"
            reference_path.write_bytes(File(reference_value).read_bytes())
            target_path.write_bytes(File(target_value).read_bytes())

            ref_reader = imageio.get_reader(str(reference_path))
            target_reader = imageio.get_reader(str(target_path))
            try:
                reference_frames = [_to_rgb(np.asarray(frame)) for frame in ref_reader]
                target_frames = [_to_rgb(np.asarray(frame)) for frame in target_reader]
                ref_meta = ref_reader.get_meta_data()
                target_meta = target_reader.get_meta_data()
            finally:
                ref_reader.close()
                target_reader.close()

            frame_count = min(len(reference_frames), len(target_frames))
            if frame_count == 0:
                raise ValueError("One or both videos contain no readable frames.")

            fps_ref = float(ref_meta.get("fps", DEFAULT_FPS) or DEFAULT_FPS)
            fps_target = float(target_meta.get("fps", DEFAULT_FPS) or DEFAULT_FPS)
            fps = min(fps_ref, fps_target) if fps_ref > 0 and fps_target > 0 else DEFAULT_FPS

            color_matcher = ColorMatcher()
            output_frames: list[np.ndarray] = []

            for idx in range(frame_count):
                ref_frame = reference_frames[idx]
                target_frame = target_frames[idx]
                out_h = min(ref_frame.shape[0], target_frame.shape[0])
                out_w = min(ref_frame.shape[1], target_frame.shape[1])
                ref_crop = ref_frame[:out_h, :out_w]
                target_crop = target_frame[:out_h, :out_w]
                output_frames.append(_frame_color_match(color_matcher, target_crop, ref_crop, method, strength))

            output_path = temp_dir / f"video_color_match_{uuid.uuid4()}.mp4"
            imageio.mimsave(str(output_path), output_frames, fps=fps)

            output_name = f"{uuid.uuid4()}.mp4"
            output_url = GriptapeNodes.StaticFilesManager().save_static_file(output_path.read_bytes(), output_name)
            self.parameter_output_values["output_video"] = VideoUrlArtifact(output_url)

        logger.info(
            "VideoColorMatchNode: method=%s strength=%.3f frames=%s output=%s",
            method,
            strength,
            frame_count,
            "set",
        )
