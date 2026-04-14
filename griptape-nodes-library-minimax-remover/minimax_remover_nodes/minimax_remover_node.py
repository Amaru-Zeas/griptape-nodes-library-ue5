from __future__ import annotations

import logging
import os
import tempfile
import uuid
import gc
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from sam_backends import create_backend

_PIPE_CACHE: dict[tuple[str, str, str], Any] = {}


def _get_best_device() -> Any:
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _get_dtype_for_device(device: Any) -> Any:
    import torch

    return torch.float16 if device.type == "cuda" else torch.float32


class MiniMaxRemoverNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.log_params = LogParameter(self)

        self.add_parameter(
            Parameter(
                name="input_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Video to clean with MiniMax remover.",
            )
        )
        self.add_parameter(
            Parameter(
                name="input_mask_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Binary mask video used when segmentation_backend is 'none'.",
            )
        )
        self.add_parameter(
            Parameter(
                name="model_dir",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional local model directory. If empty, auto-discovers a compatible snapshot in Hugging Face cache.",
            )
        )
        self.add_parameter(
            Parameter(
                name="segmentation_backend",
                input_types=["str"],
                type="str",
                default_value="none",
                traits={Options(choices=["none", "sam2", "sam3"])},
                tooltip="Mask source backend. Use none for explicit mask input.",
            )
        )
        self.add_parameter(
            Parameter(
                name="segmentation_prompt",
                input_types=["str"],
                type="str",
                default_value="person.",
                tooltip="Prompt for sam2/sam3 mask generation.",
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt_frame_idx",
                input_types=["int"],
                type="int",
                default_value=0,
                tooltip="Frame index used to seed segmentation prompts.",
            )
        )
        self.add_parameter(
            Parameter(
                name="box_threshold",
                input_types=["float"],
                type="float",
                default_value=0.30,
                tooltip="Grounding DINO box threshold for sam2 backend.",
            )
        )
        self.add_parameter(
            Parameter(
                name="text_threshold",
                input_types=["float"],
                type="float",
                default_value=0.25,
                tooltip="Grounding DINO text threshold for sam2 backend.",
            )
        )
        self.add_parameter(
            Parameter(
                name="dino_model",
                input_types=["str"],
                type="str",
                default_value="IDEA-Research/grounding-dino-base",
                tooltip="Grounding DINO repo id used for sam2 segmentation.",
            )
        )
        self.add_parameter(
            Parameter(
                name="sam2_model",
                input_types=["str"],
                type="str",
                default_value="facebook/sam2-hiera-large",
                tooltip="SAM2 repo id used for sam2 backend.",
            )
        )
        self.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                default_value=12,
                tooltip="MiniMax denoising steps.",
            )
        )
        self.add_parameter(
            Parameter(
                name="mask_dilation_iterations",
                input_types=["int"],
                type="int",
                default_value=6,
                tooltip="Mask dilation iterations used by MiniMax.",
            )
        )
        self.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                default_value=42,
                tooltip="Random seed for deterministic runs.",
            )
        )
        self.add_parameter(
            Parameter(
                name="max_frames",
                input_types=["int"],
                type="int",
                default_value=81,
                tooltip="Max frames to process from the input video.",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_fps",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Override output FPS. Use 0 to keep detected input FPS.",
            )
        )
        self.add_parameter(
            Parameter(
                name="target_width",
                input_types=["int"],
                type="int",
                default_value=0,
                tooltip="Output width. Use 0 to auto-match input width (rounded to multiple of 32).",
            )
        )
        self.add_parameter(
            Parameter(
                name="target_height",
                input_types=["int"],
                type="int",
                default_value=0,
                tooltip="Output height. Use 0 to auto-match input height (rounded to multiple of 32).",
            )
        )
        self.add_parameter(
            Parameter(
                name="clear_vram_after_run",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="If true, unloads cached pipeline and clears GPU memory cache after each run.",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Object-removed output video.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_mask_video",
                output_type="VideoUrlArtifact",
                tooltip="Mask video used for removal (input or generated).",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.log_params.add_output_parameters()

    def validate_before_node_run(self) -> list[Exception] | None:
        errors: list[Exception] = []
        if not self.get_parameter_value("input_video"):
            errors.append(ValueError("input_video is required."))

        try:
            model_dir = self._resolve_model_dir()
        except ValueError as e:
            errors.append(e)
        else:
            for name in ["vae", "transformer", "scheduler"]:
                if not (model_dir / name).exists():
                    errors.append(ValueError(f"model_dir is missing '{name}' subfolder: {model_dir / name}"))

        backend = str(self.get_parameter_value("segmentation_backend") or "none").lower()
        if backend == "none" and not self.get_parameter_value("input_mask_video"):
            errors.append(ValueError("input_mask_video is required when segmentation_backend is 'none'."))

        return errors or None

    def process(self) -> AsyncResult:
        yield lambda: self._process_with_cleanup()

    def _process_with_cleanup(self) -> None:
        clear_vram_after_run = bool(self.get_parameter_value("clear_vram_after_run") or False)
        try:
            self._process()
        finally:
            if clear_vram_after_run:
                self._clear_pipeline_cache_and_vram()

    def _process(self) -> None:  # noqa: C901, PLR0912, PLR0915
        import diffusers
        import PIL.Image
        import torch

        self.log_params.clear_logs()
        self.log_params.append_to_logs("MiniMax remover: starting...\n")

        device = _get_best_device()
        dtype = _get_dtype_for_device(device)
        self.log_params.append_to_logs(f"Device={device.type}, dtype={dtype}\n")

        input_video_path = self._artifact_to_temp_video(self.get_parameter_value("input_video"))
        detected_fps = self._get_video_fps(input_video_path)
        output_fps = float(self.get_parameter_value("output_fps") or 0.0)
        if output_fps <= 0:
            output_fps = float(detected_fps)
            self._set_parameter_value("output_fps", round(output_fps, 3))
        fps = output_fps
        self.log_params.append_to_logs(
            f"FPS: detected={detected_fps:.3f}, output={fps:.3f} (override={output_fps:.3f})\n"
        )
        frames = diffusers.utils.load_video(str(input_video_path))
        if not frames:
            raise ValueError("Input video has no decodable frames.")

        max_frames = int(self.get_parameter_value("max_frames") or len(frames))
        frames = frames[: max(1, min(max_frames, len(frames)))]
        self.log_params.append_to_logs(f"Loaded {len(frames)} frames from input video.\n")

        backend = str(self.get_parameter_value("segmentation_backend") or "none").strip().lower()
        if backend == "none":
            mask_video_path = self._artifact_to_temp_video(self.get_parameter_value("input_mask_video"))
            mask_frames = diffusers.utils.load_video(str(mask_video_path))
            if not mask_frames:
                raise ValueError("Mask video has no decodable frames.")
            mask_frames = mask_frames[: len(frames)]
        else:
            self.log_params.append_to_logs(f"Generating masks with backend={backend}...\n")
            seg_backend = create_backend(
                backend_name=backend,
                dino_model=str(self.get_parameter_value("dino_model")),
                sam2_model=str(self.get_parameter_value("sam2_model")),
            )
            mask_frames = seg_backend.generate_masks(
                frames=frames,
                prompt=str(self.get_parameter_value("segmentation_prompt") or ""),
                prompt_frame_idx=int(self.get_parameter_value("prompt_frame_idx") or 0),
                box_threshold=float(self.get_parameter_value("box_threshold") or 0.30),
                text_threshold=float(self.get_parameter_value("text_threshold") or 0.25),
                device=device,
            )
            mask_video_path = self._export_frames_to_temp_video(mask_frames, fps=fps)

        frame_count = min(len(frames), len(mask_frames))
        if frame_count == 0:
            raise ValueError("No paired frames available after input/mask alignment.")
        frames = frames[:frame_count]
        mask_frames = mask_frames[:frame_count]
        self.log_params.append_to_logs(f"Using {frame_count} paired frames.\n")
        self.log_params.append_to_logs(f"Estimated output duration: {frame_count / max(fps, 1e-6):.2f}s\n")

        images_np = np.stack([np.array(frame.convert("RGB"), dtype=np.uint8) for frame in frames], axis=0)
        masks_np = np.stack([self._mask_to_binary_rgb(np.array(frame)) for frame in mask_frames], axis=0)

        source_height, source_width = int(images_np.shape[1]), int(images_np.shape[2])
        target_width, target_height = self._resolve_target_size(source_width=source_width, source_height=source_height)
        self.log_params.append_to_logs(
            f"Resolution: source={source_width}x{source_height}, target={target_width}x{target_height}\n"
        )

        images_t = torch.from_numpy(images_np).to(torch.float32) / 127.5 - 1.0
        masks_t = torch.from_numpy(masks_np).to(torch.float32)

        model_dir = self._resolve_model_dir()
        self.log_params.append_to_logs(f"Using model_dir: {model_dir}\n")
        pipe = self._get_or_load_pipe(
            model_dir=model_dir,
            device=device,
            dtype=dtype,
        )

        with torch.no_grad():
            out = pipe(
                images=images_t,
                masks=masks_t,
                num_frames=frame_count,
                height=target_height,
                width=target_width,
                num_inference_steps=int(self.get_parameter_value("num_inference_steps") or 12),
                generator=torch.Generator(device=device).manual_seed(int(self.get_parameter_value("seed") or 42)),
                iterations=int(self.get_parameter_value("mask_dilation_iterations") or 6),
                output_type="np",
            ).frames[0]

        out = np.uint8(np.clip(out, 0.0, 1.0) * 255.0)
        out_frames = [PIL.Image.fromarray(frame) for frame in out]
        out_path = self._export_frames_to_temp_video(out_frames, fps=fps)

        self.parameter_output_values["output_video"] = self._publish_video(out_path)
        self.parameter_output_values["output_mask_video"] = self._publish_video(mask_video_path)
        self.log_params.append_to_logs("MiniMax remover: done.\n")

    def _get_or_load_pipe(self, model_dir: Path, device: Any, dtype: Any) -> Any:
        from diffusers.models import AutoencoderKLWan
        from diffusers.schedulers import UniPCMultistepScheduler
        from pipeline_minimax_remover import MinimaxRemoverPipeline
        from transformer_minimax_remover import Transformer3DModel

        key = (str(model_dir.resolve()), device.type, str(dtype))
        pipe = _PIPE_CACHE.get(key)
        if pipe is not None:
            self.log_params.append_to_logs("Reusing cached MiniMax pipeline.\n")
            return pipe

        self.log_params.append_to_logs("Loading MiniMax pipeline from local model_dir...\n")
        vae = AutoencoderKLWan.from_pretrained(str(model_dir / "vae"), torch_dtype=dtype)
        transformer = Transformer3DModel.from_pretrained(str(model_dir / "transformer"), torch_dtype=dtype)
        scheduler = UniPCMultistepScheduler.from_pretrained(str(model_dir / "scheduler"))

        pipe = MinimaxRemoverPipeline(transformer=transformer, vae=vae, scheduler=scheduler)
        pipe.to(device)
        _PIPE_CACHE.clear()
        _PIPE_CACHE[key] = pipe
        return pipe

    def _publish_video(self, video_path: Path) -> VideoUrlArtifact:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        return VideoUrlArtifact(url)

    def _get_artifact_value(self, artifact: Any) -> str:
        if artifact is None:
            raise ValueError("Expected video artifact but got None.")
        if isinstance(artifact, str):
            return artifact
        if isinstance(artifact, dict):
            value = artifact.get("value")
            if isinstance(value, str) and value:
                return value
            raise ValueError("Video artifact dict is missing a usable 'value'.")
        value = getattr(artifact, "value", None)
        if isinstance(value, str) and value:
            return value
        raise ValueError("Unsupported video artifact input type.")

    def _artifact_to_temp_video(self, artifact: Any) -> Path:
        value = self._get_artifact_value(artifact)
        parsed = urlparse(value)
        source_path = parsed.path if parsed.scheme else value
        suffix = Path(source_path).suffix or ".mp4"
        if not suffix.startswith(".") or any(ch in suffix for ch in '<>:"/\\|?*'):
            suffix = ".mp4"
        fd, temp_path_str = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        Path(temp_path_str).unlink(missing_ok=True)
        out_path = Path(temp_path_str)
        out_path.write_bytes(File(value).read_bytes())
        return out_path

    def _export_frames_to_temp_video(self, frames: list[Any], fps: float) -> Path:
        import diffusers

        if not frames:
            raise ValueError("No frames available to export.")
        fd, temp_path_str = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        Path(temp_path_str).unlink(missing_ok=True)
        out_path = Path(temp_path_str)
        diffusers.utils.export_to_video(frames, str(out_path), fps=max(1, int(round(fps))))
        return out_path

    def _get_video_fps(self, video_path: Path, default_fps: float = 15.0) -> float:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return default_fps
        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            if not fps or fps <= 0:
                return default_fps
            return float(fps)
        finally:
            cap.release()

    def _resolve_model_dir(self) -> Path:
        model_dir = str(self.get_parameter_value("model_dir") or "").strip()
        if model_dir:
            return Path(model_dir)

        candidates = self._find_hf_cache_model_dirs()
        if not candidates:
            raise ValueError(
                "No MiniMax model directory found. Set model_dir or place a compatible HF snapshot with "
                "'vae', 'transformer', and 'scheduler' subfolders in the Hugging Face cache."
            )
        return candidates[0]

    def _find_hf_cache_model_dirs(self) -> list[Path]:
        try:
            from huggingface_hub.constants import HF_HUB_CACHE
        except Exception:
            return []

        cache_root = Path(HF_HUB_CACHE)
        if not cache_root.exists():
            return []

        candidates: list[tuple[int, float, Path]] = []
        for repo_dir in cache_root.iterdir():
            if not repo_dir.is_dir():
                continue
            if not repo_dir.name.startswith("models--"):
                continue

            snapshots_dir = repo_dir / "snapshots"
            if not snapshots_dir.exists():
                continue

            repo_hint = repo_dir.name.lower()
            score = int("minimax" in repo_hint) + int("remover" in repo_hint)
            for snapshot_dir in snapshots_dir.iterdir():
                if not snapshot_dir.is_dir():
                    continue
                if all((snapshot_dir / name).is_dir() for name in ("vae", "transformer", "scheduler")):
                    mtime = snapshot_dir.stat().st_mtime
                    candidates.append((score, mtime, snapshot_dir))

        candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [path for _, _, path in candidates]

    def _mask_to_binary_rgb(self, frame: np.ndarray) -> np.ndarray:
        if frame.ndim == 2:
            gray = frame
        elif frame.ndim == 3:
            gray = frame[:, :, 0]
        else:
            raise ValueError(f"Unsupported mask frame shape: {frame.shape}")
        binary = (gray > 20).astype(np.float32)
        return binary[:, :, None]

    def _resolve_target_size(self, source_width: int, source_height: int) -> tuple[int, int]:
        user_width = int(self.get_parameter_value("target_width") or 0)
        user_height = int(self.get_parameter_value("target_height") or 0)

        if user_width > 0:
            width = user_width
        else:
            width = source_width

        if user_height > 0:
            height = user_height
        else:
            height = source_height

        width = self._round_down_to_multiple(width, 32)
        height = self._round_down_to_multiple(height, 32)
        if user_width <= 0:
            self._set_parameter_value("target_width", width)
        if user_height <= 0:
            self._set_parameter_value("target_height", height)
        return width, height

    def _round_down_to_multiple(self, value: int, multiple: int) -> int:
        value = max(multiple, int(value))
        return max(multiple, (value // multiple) * multiple)

    def _set_parameter_value(self, name: str, value: Any) -> None:
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name=name, value=value, node_name=self.name))

    def _clear_pipeline_cache_and_vram(self) -> None:
        cleared = len(_PIPE_CACHE)
        for pipe in list(_PIPE_CACHE.values()):
            try:
                if hasattr(pipe, "to"):
                    pipe.to("cpu")
            except Exception:
                pass
        _PIPE_CACHE.clear()

        gc.collect()

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
        except Exception:
            pass

        self.log_params.append_to_logs(
            f"clear_vram_after_run=true -> unloaded {cleared} cached pipeline(s) and cleared device caches.\n"
        )
