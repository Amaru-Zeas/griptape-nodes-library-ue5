from __future__ import annotations

import numpy as np
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter

from minimax_remover_node import MiniMaxRemoverNode, _get_best_device, _get_dtype_for_device


class MiniMaxRemoverNodeV2(MiniMaxRemoverNode):
    """Mask-input-only MiniMax remover node.

    This v2 node intentionally removes built-in segmentation controls and requires
    an explicit mask video input to keep behavior predictable and reduce artifacts
    from prompt-driven mask drift.
    """

    def __init__(self, **kwargs) -> None:
        ControlNode.__init__(self, **kwargs)
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
                tooltip="Required binary mask video (white = remove, black = keep).",
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
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                default_value=14,
                tooltip="MiniMax denoising steps. Higher can reduce artifacts but costs more time.",
            )
        )
        self.add_parameter(
            Parameter(
                name="mask_dilation_iterations",
                input_types=["int"],
                type="int",
                default_value=4,
                tooltip="Mask dilation iterations. Lower values preserve detail; higher values remove halo edges.",
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
                tooltip="Mask video actually used for removal.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.log_params.add_output_parameters()

    def validate_before_node_run(self) -> list[Exception] | None:
        errors: list[Exception] = []
        if not self.get_parameter_value("input_video"):
            errors.append(ValueError("input_video is required."))
        if not self.get_parameter_value("input_mask_video"):
            errors.append(ValueError("input_mask_video is required in MiniMaxRemoverNodeV2."))

        try:
            model_dir = self._resolve_model_dir()
        except ValueError as e:
            errors.append(e)
        else:
            for name in ["vae", "transformer", "scheduler"]:
                if not (model_dir / name).exists():
                    errors.append(ValueError(f"model_dir is missing '{name}' subfolder: {model_dir / name}"))

        return errors or None

    def process(self) -> AsyncResult:
        yield lambda: self._process_with_cleanup()

    def _process(self) -> None:
        import diffusers
        import PIL.Image
        import torch

        self.log_params.clear_logs()
        self.log_params.append_to_logs("MiniMax remover v2: starting...\n")

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

        mask_video_path = self._artifact_to_temp_video(self.get_parameter_value("input_mask_video"))
        mask_frames = diffusers.utils.load_video(str(mask_video_path))
        if not mask_frames:
            raise ValueError("Mask video has no decodable frames.")

        max_frames = int(self.get_parameter_value("max_frames") or len(frames))
        frames = frames[: max(1, min(max_frames, len(frames)))]
        mask_frames = mask_frames[: max(1, min(max_frames, len(mask_frames)))]

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
                num_inference_steps=int(self.get_parameter_value("num_inference_steps") or 14),
                generator=torch.Generator(device=device).manual_seed(int(self.get_parameter_value("seed") or 42)),
                iterations=int(self.get_parameter_value("mask_dilation_iterations") or 4),
                output_type="np",
            ).frames[0]

        out = np.uint8(np.clip(out, 0.0, 1.0) * 255.0)
        out_frames = [PIL.Image.fromarray(frame) for frame in out]
        out_path = self._export_frames_to_temp_video(out_frames, fps=fps)

        self.parameter_output_values["output_video"] = self._publish_video(out_path)
        self.parameter_output_values["output_mask_video"] = self._publish_video(mask_video_path)
        self.log_params.append_to_logs("MiniMax remover v2: done.\n")
