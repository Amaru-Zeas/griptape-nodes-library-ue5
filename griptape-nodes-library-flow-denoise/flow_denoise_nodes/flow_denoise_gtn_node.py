from __future__ import annotations

import io
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import requests
import torch
from PIL import Image
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.options import Options

from flow_denoise_core import ExtractNoise, SelectiveDenoise, TemporalFlowAverage

DEFAULT_STATICFILES_DIR = Path(r"C:\Users\AI PC\GriptapeNodes\staticfiles")


def _candidate_paths(raw_path: str) -> list[Path]:
    text = str(raw_path or "").strip()
    if not text:
        return []
    normalized = text.replace("\\", "/")
    candidates = [Path(text)]
    if normalized.startswith("{inputs}/"):
        suffix = normalized[len("{inputs}/") :]
        candidates.append(Path.home() / "GriptapeNodes" / "inputs" / suffix)
    if normalized.startswith("/staticfiles/"):
        suffix = normalized.split("/staticfiles/", 1)[1].strip().lstrip("/")
        if suffix:
            static_dir = Path(os.environ.get("GTN_STATICFILES_DIR", str(DEFAULT_STATICFILES_DIR)))
            candidates.append(static_dir / suffix)
    return candidates


def _download_http_bytes(url: str) -> bytes | None:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content if response.content else None
    except Exception:
        return None


def _read_image_bytes(value: Any, depth: int = 0) -> bytes:
    if depth > 8:
        raise ValueError("Image input nesting too deep.")
    if value is None:
        raise ValueError("Missing image value.")
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith(("http://", "https://")):
            content = _download_http_bytes(candidate)
            if content:
                return content
        if candidate.startswith("file://"):
            candidate = candidate.replace("file:///", "").replace("file://", "")
        for path in _candidate_paths(candidate):
            if path.exists() and path.is_file():
                return path.read_bytes()
        raise ValueError(f"Unsupported image string source: {candidate}")
    if isinstance(value, dict):
        for key in ("value", "image", "url", "path", "image_data"):
            if key in value:
                return _read_image_bytes(value[key], depth + 1)
        raise ValueError("Dict image input does not include a supported image field.")

    raw_value = getattr(value, "value", None)
    if raw_value is not None:
        return _read_image_bytes(raw_value, depth + 1)
    raw_url = getattr(value, "url", None)
    if raw_url is not None:
        return _read_image_bytes(raw_url, depth + 1)
    raw_path = getattr(value, "path", None)
    if raw_path is not None:
        return _read_image_bytes(raw_path, depth + 1)
    raise ValueError(f"Unsupported image input type: {type(value).__name__}")


def _normalize_frame_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _frame_list_to_tensor(value: Any, *, resize_to_first: bool = True) -> torch.Tensor:
    frames = _normalize_frame_list(value)
    if not frames:
        raise ValueError("No frames provided.")

    pil_frames: list[Image.Image] = []
    first_size: tuple[int, int] | None = None

    for frame in frames:
        raw = _read_image_bytes(frame)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if first_size is None:
            first_size = img.size
        elif resize_to_first and img.size != first_size:
            img = img.resize(first_size, Image.Resampling.LANCZOS)
        pil_frames.append(img)

    arr = np.stack([np.asarray(p).astype(np.float32) / 255.0 for p in pil_frames], axis=0)
    return torch.from_numpy(arr)


def _resolve_video_input_to_local_path(value: Any, depth: int = 0) -> tuple[str, bool]:
    if depth > 8:
        raise ValueError("Video input nesting too deep.")
    if value is None:
        raise ValueError("No video input provided.")

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            raise ValueError("Empty video input string.")
        if candidate.startswith(("http://", "https://")):
            raw = _download_http_bytes(candidate)
            if not raw:
                raise ValueError(f"Failed to download video from URL: {candidate}")
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp.write(raw)
            tmp.close()
            return tmp.name, True
        if candidate.startswith("file://"):
            candidate = candidate.replace("file:///", "").replace("file://", "")
        for path in _candidate_paths(candidate):
            if path.exists() and path.is_file():
                return str(path), False
        raise ValueError(f"Video path not found: {candidate}")

    if isinstance(value, bytes):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(value)
        tmp.close()
        return tmp.name, True

    if isinstance(value, dict):
        for key in ("value", "video", "video_url", "url", "path", "video_path"):
            if key in value and value[key] is not None:
                return _resolve_video_input_to_local_path(value[key], depth + 1)
        raise ValueError("Video dict input does not include a supported video field.")

    raw_value = getattr(value, "value", None)
    if raw_value is not None:
        return _resolve_video_input_to_local_path(raw_value, depth + 1)
    raw_url = getattr(value, "url", None)
    if raw_url is not None:
        return _resolve_video_input_to_local_path(raw_url, depth + 1)
    raw_path = getattr(value, "path", None)
    if raw_path is not None:
        return _resolve_video_input_to_local_path(raw_path, depth + 1)

    raise ValueError(f"Unsupported video input type: {type(value).__name__}")


def _video_to_tensor(video_value: Any, frame_step: int = 1, max_frames: int = 0) -> torch.Tensor:
    local_path, cleanup = _resolve_video_input_to_local_path(video_value)
    try:
        video = None
        decode_error = None
        try:
            from torchvision.io import read_video

            video, _, _ = read_video(local_path, pts_unit="sec")  # [T, H, W, C] uint8
        except Exception as exc:
            decode_error = exc

        # Fallback path when torchvision video decode is unavailable (e.g. PyAV missing).
        if video is None or getattr(video, "numel", lambda: 0)() == 0:
            try:
                import cv2

                cap = cv2.VideoCapture(local_path)
                frames: list[np.ndarray] = []
                while True:
                    ok, frame_bgr = cap.read()
                    if not ok:
                        break
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                cap.release()
                if not frames:
                    raise ValueError("No frames decoded from video input.")
                video = torch.from_numpy(np.stack(frames, axis=0))
            except Exception as cv_exc:
                if decode_error is not None:
                    raise ValueError(
                        "Video decode failed with torchvision and OpenCV fallback. "
                        f"torchvision error: {decode_error}; cv2 error: {cv_exc}"
                    ) from cv_exc
                raise
    finally:
        if cleanup:
            try:
                os.remove(local_path)
            except Exception:
                pass

    if video is None or video.numel() == 0:
        raise ValueError("No frames decoded from video input.")

    step = max(1, int(frame_step or 1))
    video = video[::step]
    if max_frames and int(max_frames) > 0:
        video = video[: int(max_frames)]
    if video.shape[0] == 0:
        raise ValueError("Video decoding produced 0 frames after sampling.")

    return video.to(dtype=torch.float32) / 255.0


def _tensor_to_image_artifacts(tensor_bhwc: torch.Tensor, base_name: str) -> list[ImageArtifact]:
    tensor = tensor_bhwc.detach().cpu().clamp(0.0, 1.0)
    artifacts: list[ImageArtifact] = []
    ts = int(time.time() * 1000)
    for idx in range(tensor.shape[0]):
        frame = (tensor[idx].numpy() * 255.0).round().astype(np.uint8)
        img = Image.fromarray(frame, mode="RGB")
        out = io.BytesIO()
        img.save(out, format="PNG")
        file_name = f"{base_name}_{ts}_{idx:05d}.png"
        artifacts.append(
            ImageArtifact(
                value=out.getvalue(),
                width=img.width,
                height=img.height,
                format="png",
                name=file_name,
            )
        )
    return artifacts


class TemporalFlowAverageNode(DataNode):
    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "FlowDenoise",
            "description": "Motion-compensated temporal averaging with MEMFOF/RAFT.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="frames",
                input_types=["ImageArtifact", "ImageUrlArtifact", "list[ImageArtifact]", "list"],
                type="list[ImageArtifact]",
                tooltip="Input frame sequence. If provided, this takes precedence over input_video.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="input_video",
                input_types=["VideoArtifact", "VideoUrlArtifact", "str", "dict"],
                type="VideoUrlArtifact",
                tooltip="Optional direct video input. Used only when frames is empty.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="video_frame_step",
                input_types=["int"],
                type="int",
                default_value=1,
                tooltip="Use every Nth video frame when decoding input_video.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="max_video_frames",
                input_types=["int"],
                type="int",
                default_value=0,
                tooltip="Maximum decoded frames from input_video (0 = all frames).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(Parameter(name="window_size", input_types=["int"], type="int", default_value=2, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="weight_decay", input_types=["float"], type="float", default_value=0.8, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(
            Parameter(
                name="flow_model",
                input_types=["str"],
                type="str",
                default_value="memfof",
                traits={Options(choices=["memfof", "raft_small", "raft_large"])},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(Parameter(name="flow_iterations", input_types=["int"], type="int", default_value=8, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="color_threshold", input_types=["float"], type="float", default_value=0.04, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="scene_threshold", input_types=["float"], type="float", default_value=0.06, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="batch_size", input_types=["int"], type="int", default_value=1, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))

        self.add_parameter(
            Parameter(
                name="clean_frames",
                output_type="list[ImageArtifact]",
                tooltip="Temporally denoised frame sequence.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="weight_map_frames",
                output_type="list[ImageArtifact]",
                tooltip="Per-frame confidence weight map previews.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        frames_value = self.parameter_values.get("frames")
        if _normalize_frame_list(frames_value):
            images = _frame_list_to_tensor(frames_value)
        else:
            images = _video_to_tensor(
                self.parameter_values.get("input_video"),
                frame_step=int(self.parameter_values.get("video_frame_step") or 1),
                max_frames=int(self.parameter_values.get("max_video_frames") or 0),
            )
        core = TemporalFlowAverage()
        clean, weight_map = core.denoise(
            images=images,
            window_size=int(self.parameter_values.get("window_size") or 2),
            weight_decay=float(self.parameter_values.get("weight_decay") or 0.8),
            flow_model=str(self.parameter_values.get("flow_model") or "memfof"),
            flow_iterations=int(self.parameter_values.get("flow_iterations") or 8),
            color_threshold=float(self.parameter_values.get("color_threshold") or 0.04),
            scene_threshold=float(self.parameter_values.get("scene_threshold") or 0.06),
            batch_size=int(self.parameter_values.get("batch_size") or 1),
        )
        self.parameter_output_values["clean_frames"] = _tensor_to_image_artifacts(clean, "flow_denoise_clean")
        self.parameter_output_values["weight_map_frames"] = _tensor_to_image_artifacts(weight_map, "flow_denoise_weight")


class ExtractNoiseNode(DataNode):
    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "FlowDenoise",
            "description": "Extract total/chroma/luma noise from original-clean frame sequences.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(Parameter(name="original_frames", input_types=["ImageArtifact", "ImageUrlArtifact", "list[ImageArtifact]", "list"], type="list[ImageArtifact]", allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="clean_frames", input_types=["ImageArtifact", "ImageUrlArtifact", "list[ImageArtifact]", "list"], type="list[ImageArtifact]", allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="noise_amplify", input_types=["float"], type="float", default_value=5.0, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(
            Parameter(
                name="color_space",
                input_types=["str"],
                type="str",
                default_value="YCbCr",
                traits={Options(choices=["YCbCr", "HSV", "LAB"])},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="noise_preview",
                input_types=["str"],
                type="str",
                default_value="heatmap",
                traits={Options(choices=["heatmap", "signed", "gray"])},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(Parameter(name="noise_total_frames", output_type="list[ImageArtifact]", allowed_modes={ParameterMode.OUTPUT}))
        self.add_parameter(Parameter(name="noise_chroma_frames", output_type="list[ImageArtifact]", allowed_modes={ParameterMode.OUTPUT}))
        self.add_parameter(Parameter(name="noise_luma_frames", output_type="list[ImageArtifact]", allowed_modes={ParameterMode.OUTPUT}))

    def process(self) -> None:
        original = _frame_list_to_tensor(self.parameter_values.get("original_frames"))
        clean = _frame_list_to_tensor(self.parameter_values.get("clean_frames"))
        if original.shape[0] != clean.shape[0]:
            raise ValueError("original_frames and clean_frames must contain the same number of frames.")

        core = ExtractNoise()
        total, chroma, luma = core.extract(
            original=original,
            clean=clean,
            noise_amplify=float(self.parameter_values.get("noise_amplify") or 5.0),
            color_space=str(self.parameter_values.get("color_space") or "YCbCr"),
            noise_preview=str(self.parameter_values.get("noise_preview") or "heatmap"),
        )

        self.parameter_output_values["noise_total_frames"] = _tensor_to_image_artifacts(total, "flow_noise_total")
        self.parameter_output_values["noise_chroma_frames"] = _tensor_to_image_artifacts(chroma, "flow_noise_chroma")
        self.parameter_output_values["noise_luma_frames"] = _tensor_to_image_artifacts(luma, "flow_noise_luma")


class SelectiveDenoiseNode(DataNode):
    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "FlowDenoise",
            "description": "Blend original and clean frames with independent chroma/luma control.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(Parameter(name="original_frames", input_types=["ImageArtifact", "ImageUrlArtifact", "list[ImageArtifact]", "list"], type="list[ImageArtifact]", allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="clean_frames", input_types=["ImageArtifact", "ImageUrlArtifact", "list[ImageArtifact]", "list"], type="list[ImageArtifact]", allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="chroma_strength", input_types=["float"], type="float", default_value=0.8, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="luma_strength", input_types=["float"], type="float", default_value=0.3, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(
            Parameter(
                name="color_space",
                input_types=["str"],
                type="str",
                default_value="YCbCr",
                traits={Options(choices=["YCbCr", "HSV", "LAB"])},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(Parameter(name="clamp_output", input_types=["bool"], type="bool", default_value=True, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))

        self.add_parameter(Parameter(name="denoised_frames", output_type="list[ImageArtifact]", allowed_modes={ParameterMode.OUTPUT}))

    def process(self) -> None:
        original = _frame_list_to_tensor(self.parameter_values.get("original_frames"))
        clean = _frame_list_to_tensor(self.parameter_values.get("clean_frames"))
        if original.shape[0] != clean.shape[0]:
            raise ValueError("original_frames and clean_frames must contain the same number of frames.")

        core = SelectiveDenoise()
        denoised, = core.denoise(
            original=original,
            clean=clean,
            chroma_strength=float(self.parameter_values.get("chroma_strength") or 0.8),
            luma_strength=float(self.parameter_values.get("luma_strength") or 0.3),
            color_space=str(self.parameter_values.get("color_space") or "YCbCr"),
            clamp_output=bool(self.parameter_values.get("clamp_output") if self.parameter_values.get("clamp_output") is not None else True),
        )
        self.parameter_output_values["denoised_frames"] = _tensor_to_image_artifacts(denoised, "flow_denoised")
