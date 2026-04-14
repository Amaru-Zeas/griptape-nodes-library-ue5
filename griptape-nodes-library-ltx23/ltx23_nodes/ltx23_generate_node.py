from __future__ import annotations

import json
import os
import random
import shlex
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options


class LTX23GenerateNode(ControlNode):
    """Run LTX-2.3 pipelines with GTN-friendly controls and LoRA stacking."""

    DEFAULT_LTX_REPO_DIR = r"A:\GriptapeSketchFab\LTX-2"
    DEFAULT_PYTHON_EXECUTABLE = r"A:\GriptapeSketchFab\LTX-2\.venv\Scripts\python.exe"
    DEFAULT_MODELS_ROOT = r"A:\GriptapeSketchFab\models\ltx-2.3"
    DEFAULT_DEV_CHECKPOINT = "ltx-2.3-22b-dev.safetensors"
    DEFAULT_DISTILLED_CHECKPOINT = "ltx-2.3-22b-distilled.safetensors"
    DEFAULT_SPATIAL_X2 = "ltx-2.3-spatial-upscaler-x2-1.0.safetensors"
    DEFAULT_SPATIAL_X15 = "ltx-2.3-spatial-upscaler-x1.5-1.0.safetensors"
    DEFAULT_DISTILLED_LORA = "ltx-2.3-22b-distilled-lora-384.safetensors"
    DEFAULT_GEMMA_ROOT = r"A:\GriptapeSketchFab\models\ltx-2.3\gemma-12b"
    LEGACY_GEMMA_ROOT = r"A:\GriptapeSketchFab\models\ltx-2.3\gemma"
    DEFAULT_DEV_CHECKPOINT_PATH = r"A:\GriptapeSketchFab\models\ltx-2.3\checkpoints\ltx-2.3-22b-dev.safetensors"
    DEFAULT_DISTILLED_CHECKPOINT_PATH = (
        r"A:\GriptapeSketchFab\models\ltx-2.3\checkpoints\ltx-2.3-22b-distilled.safetensors"
    )
    DEFAULT_SPATIAL_UPSAMPLER_X2_PATH = (
        r"A:\GriptapeSketchFab\models\ltx-2.3\upscalers\ltx-2.3-spatial-upscaler-x2-1.0.safetensors"
    )
    DEFAULT_DISTILLED_LORA_PATH = (
        r"A:\GriptapeSketchFab\models\ltx-2.3\distilled_lora\ltx-2.3-22b-distilled-lora-384.safetensors"
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.log_params = LogParameter(self)

        with ParameterGroup(name="1) Prompt and Pipeline", collapsed=False) as prompt_group:
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                default_value="A cinematic shot of a futuristic city at sunset.",
                tooltip="Prompt used for generation.",
            )
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                default_value="low quality, artifacts, blurry",
                tooltip="Negative prompt for non-distilled two-stage modules.",
            )
            Parameter(
                name="pipeline_module",
                input_types=["str"],
                type="str",
                default_value="ti2vid_two_stages",
                traits={
                    Options(choices=["ti2vid_two_stages", "ti2vid_two_stages_hq", "distilled", "ic_lora", "retake"]),
                },
                tooltip="LTX pipeline module name (without ltx_pipelines. prefix).",
            )
            Parameter(
                name="enhance_prompt",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Enable LTX prompt enhancement if supported by selected module.",
            )
        self.add_node_element(prompt_group)

        with ParameterGroup(name="2) Model and Runtime Paths", collapsed=True) as model_group:
            Parameter(
                name="ltx_repo_dir",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_LTX_REPO_DIR,
                tooltip="Local path to LTX-2 repository root.",
            )
            Parameter(
                name="python_executable",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_PYTHON_EXECUTABLE,
                tooltip="Python executable from the environment where ltx_pipelines is installed.",
            )
            Parameter(
                name="models_root",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_MODELS_ROOT,
                tooltip="Root folder for local models downloaded by LTX-2.3 Model Downloader.",
            )
            Parameter(
                name="auto_resolve_model_paths",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Auto-fill checkpoint/upscaler/distilled LoRA/Gemma paths from models_root when empty.",
            )
            Parameter(
                name="checkpoint_variant",
                input_types=["str"],
                type="str",
                default_value="dev",
                traits={Options(choices=["dev", "distilled"])},
                tooltip="Used when checkpoint_path is empty and auto_resolve_model_paths=true.",
            )
            Parameter(
                name="spatial_upsampler_variant",
                input_types=["str"],
                type="str",
                default_value="x2",
                traits={Options(choices=["x2", "x1.5"])},
                tooltip="Used when spatial_upsampler_path is empty and auto_resolve_model_paths=true.",
            )
            Parameter(
                name="checkpoint_path",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_DEV_CHECKPOINT_PATH,
                tooltip="Path to LTX model checkpoint (.safetensors).",
            )
            Parameter(
                name="clip_model_path",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_GEMMA_ROOT,
                tooltip="Compatibility slot for CLIP-style workflows. LTX pipeline modules do not currently consume this directly.",
            )
            Parameter(
                name="vae_model_path",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_DEV_CHECKPOINT_PATH,
                tooltip="Compatibility slot for VAE-style workflows. LTX pipeline modules do not currently consume this directly.",
            )
            Parameter(
                name="gemma_root",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_GEMMA_ROOT,
                tooltip="Path to Gemma model assets directory.",
            )
            Parameter(
                name="spatial_upsampler_path",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_SPATIAL_UPSAMPLER_X2_PATH,
                tooltip="Path to LTX spatial upsampler checkpoint.",
            )
            Parameter(
                name="distilled_lora_path",
                input_types=["str"],
                type="str",
                default_value=self.DEFAULT_DISTILLED_LORA_PATH,
                tooltip="Distilled LoRA checkpoint path (required by two-stage non-distilled modules).",
            )
            Parameter(
                name="distilled_lora_strength",
                input_types=["float"],
                type="float",
                default_value=0.8,
                tooltip="Strength value paired with distilled_lora_path.",
            )
            Parameter(
                name="lora_stack_json",
                input_types=["str"],
                type="str",
                default_value="[]",
                tooltip="JSON list of runtime LoRAs. Example: [{\"path\":\"...\",\"strength\":0.7}].",
            )
        self.add_node_element(model_group)

        with ParameterGroup(name="3) Image/Video Conditioning", collapsed=True) as conditioning_group:
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Optional conditioning image for image-to-video style runs.",
            )
            Parameter(
                name="image_frame_idx",
                input_types=["int"],
                type="int",
                default_value=0,
                tooltip="Frame index where input_image is applied (--image PATH FRAME_IDX STRENGTH).",
            )
            Parameter(
                name="image_strength",
                input_types=["float"],
                type="float",
                default_value=1.0,
                tooltip="Conditioning strength for input_image.",
            )
            Parameter(
                name="image_crf",
                input_types=["int"],
                type="int",
                default_value=23,
                tooltip="Optional image conditioning CRF value used by LTX CLI.",
            )
            Parameter(
                name="input_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Optional video input used by ic_lora (video conditioning) or retake (source clip).",
            )
            Parameter(
                name="outpaint_auto_letterbox_to_target",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="For ic_lora: letterbox input_video into target width/height with pure black bars before conditioning.",
            )
            Parameter(
                name="video_condition_strength",
                input_types=["float"],
                type="float",
                default_value=1.0,
                tooltip="Strength paired with --video-conditioning for ic_lora.",
            )
            Parameter(
                name="conditioning_attention_mask_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Optional mask video for ic_lora --conditioning-attention-mask.",
            )
            Parameter(
                name="outpaint_auto_mask_from_black",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="If true and mask input is empty, builds conditioning mask automatically from near-black pixels.",
            )
            Parameter(
                name="outpaint_black_threshold",
                input_types=["int"],
                type="int",
                default_value=8,
                tooltip="Pixels with max(R,G,B) <= threshold are treated as outpaint regions when auto mask is enabled.",
            )
            Parameter(
                name="outpaint_min_mask_ratio_warn",
                input_types=["float"],
                type="float",
                default_value=0.05,
                tooltip="Warn if auto-generated mask covers less than this fraction of pixels.",
            )
            Parameter(
                name="outpaint_mask_white_is_keep",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="If true, auto mask uses white=preserve area and black=generate area (recommended for IC-LoRA outpaint).",
            )
            Parameter(
                name="outpaint_strict_preserve_center",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="For ic_lora outpaint, force exact center preservation by compositing original non-black area back on output.",
            )
            Parameter(
                name="outpaint_gamma_fix",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Apply gamma pre/post roundtrip for dark scenes (ic_lora only).",
            )
            Parameter(
                name="outpaint_gamma_value",
                input_types=["float"],
                type="float",
                default_value=2.0,
                tooltip="Gamma value for outpaint gamma fix. Inverse is applied to output automatically.",
            )
            Parameter(
                name="conditioning_attention_strength",
                input_types=["float"],
                type="float",
                default_value=1.0,
                tooltip="Strength paired with conditioning_attention_mask_video.",
            )
            Parameter(
                name="retake_start_time",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Retake start time in seconds (retake pipeline only).",
            )
            Parameter(
                name="retake_end_time",
                input_types=["float"],
                type="float",
                default_value=2.0,
                tooltip="Retake end time in seconds (retake pipeline only).",
            )
        self.add_node_element(conditioning_group)

        with ParameterGroup(name="4) Generation Settings", collapsed=True) as generation_group:
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                default_value=768,
                tooltip="Output width (must be divisible by 32).",
            )
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                default_value=512,
                tooltip="Output height (must be divisible by 32).",
            )
            Parameter(
                name="num_frames",
                input_types=["int"],
                type="int",
                default_value=121,
                tooltip="Frame count (8k+1 shape recommended).",
            )
            Parameter(
                name="frame_rate",
                input_types=["float"],
                type="float",
                default_value=25.0,
                tooltip="Output FPS.",
            )
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                default_value=40,
                tooltip="Inference step count (used by two-stage modules).",
            )
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                default_value=42,
                tooltip="Seed for deterministic generation.",
            )
            Parameter(
                name="randomize_seed",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="If true, ignores seed input and chooses a fresh random seed each run.",
            )
            Parameter(
                name="video_cfg_scale",
                input_types=["float"],
                type="float",
                default_value=3.0,
                tooltip="Video CFG guidance scale for two-stage modules.",
            )
            Parameter(
                name="audio_cfg_scale",
                input_types=["float"],
                type="float",
                default_value=7.0,
                tooltip="Audio CFG guidance scale for two-stage modules.",
            )
            Parameter(
                name="extra_cli_args",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Extra CLI arguments appended at the end of command.",
            )
        self.add_node_element(generation_group)

        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Generated LTX output video.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="used_seed",
                output_type="int",
                tooltip="Actual seed used for this generation run.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        with ParameterGroup(name="5) Debug", collapsed=True) as debug_group:
            Parameter(
                name="debug_command",
                output_type="str",
                tooltip="Final command that was executed.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        self.add_node_element(debug_group)
        self.log_params.add_output_parameters()

    def validate_before_node_run(self) -> list[Exception] | None:
        errors: list[Exception] = []
        prompt = str(self.get_parameter_value("prompt") or "").strip()
        if not prompt:
            errors.append(ValueError("prompt is required."))

        repo_raw = str(self.get_parameter_value("ltx_repo_dir") or "").strip()
        repo_dir = Path(repo_raw) if repo_raw else None
        if repo_dir is None:
            errors.append(ValueError("ltx_repo_dir is required."))
        elif not repo_dir.exists():
            errors.append(ValueError(f"ltx_repo_dir does not exist: {repo_dir}"))
        elif not (repo_dir / "packages" / "ltx-pipelines").exists():
            errors.append(ValueError(f"ltx_repo_dir does not look like LTX-2 repo: {repo_dir}"))

        paths = self._resolve_model_paths()
        checkpoint_path = paths["checkpoint_path"]
        if checkpoint_path is None:
            errors.append(ValueError("checkpoint_path is required."))
        elif not checkpoint_path.exists():
            errors.append(ValueError(f"checkpoint_path does not exist: {checkpoint_path}"))

        gemma_root = paths["gemma_root"]
        if gemma_root is None:
            errors.append(ValueError("gemma_root is required."))
        elif not gemma_root.exists():
            errors.append(ValueError(f"gemma_root does not exist: {gemma_root}"))

        spatial_upsampler_path = paths["spatial_upsampler_path"]
        if spatial_upsampler_path is None:
            errors.append(ValueError("spatial_upsampler_path is required."))
        elif not spatial_upsampler_path.exists():
            errors.append(ValueError(f"spatial_upsampler_path does not exist: {spatial_upsampler_path}"))

        pipeline_module = str(self.get_parameter_value("pipeline_module") or "ti2vid_two_stages").strip()
        if pipeline_module in {"ti2vid_two_stages", "ti2vid_two_stages_hq"}:
            distilled_lora_path = paths["distilled_lora_path"]
            if distilled_lora_path is None:
                errors.append(ValueError("distilled_lora_path is required for two-stage non-distilled modules."))
            elif not distilled_lora_path.exists():
                errors.append(ValueError(f"distilled_lora_path does not exist: {distilled_lora_path}"))
        if pipeline_module in {"ti2vid_two_stages", "ti2vid_two_stages_hq", "distilled", "ic_lora"}:
            if spatial_upsampler_path is None:
                errors.append(ValueError("spatial_upsampler_path is required for selected pipeline_module."))
            elif not spatial_upsampler_path.exists():
                errors.append(ValueError(f"spatial_upsampler_path does not exist: {spatial_upsampler_path}"))
        if pipeline_module in {"ic_lora", "retake"} and not self.get_parameter_value("input_video"):
            errors.append(ValueError("input_video is required for ic_lora and retake pipelines."))
        if pipeline_module == "retake":
            start_time = float(self.get_parameter_value("retake_start_time") or 0.0)
            end_time = float(self.get_parameter_value("retake_end_time") or 0.0)
            if end_time <= start_time:
                errors.append(ValueError("retake_end_time must be greater than retake_start_time."))

        clip_model_path_raw = str(self.get_parameter_value("clip_model_path") or "").strip()
        if clip_model_path_raw and not Path(clip_model_path_raw).exists():
            errors.append(ValueError(f"clip_model_path does not exist: {clip_model_path_raw}"))

        vae_model_path_raw = str(self.get_parameter_value("vae_model_path") or "").strip()
        if vae_model_path_raw and not Path(vae_model_path_raw).exists():
            errors.append(ValueError(f"vae_model_path does not exist: {vae_model_path_raw}"))

        width = int(self.get_parameter_value("width") or 0)
        height = int(self.get_parameter_value("height") or 0)
        if width <= 0 or height <= 0:
            errors.append(ValueError("width and height must be > 0."))

        num_frames = int(self.get_parameter_value("num_frames") or 0)
        if num_frames <= 0:
            errors.append(ValueError("num_frames must be > 0."))
        if (num_frames - 1) % 8 != 0:
            errors.append(ValueError("num_frames should follow 8k+1 pattern (for example 121, 129, 137)."))

        try:
            self._parse_lora_stack_json(str(self.get_parameter_value("lora_stack_json") or "[]"))
        except ValueError as e:
            errors.append(e)

        return errors or None

    def process(self) -> AsyncResult:
        yield lambda: self._process()

    def _process(self) -> None:
        self.log_params.clear_logs()
        self.log_params.append_to_logs("LTX-2.3 generation: preparing command...\n")

        pipeline_module = str(self.get_parameter_value("pipeline_module") or "ti2vid_two_stages").strip()
        python_executable = str(self.get_parameter_value("python_executable") or "python").strip() or "python"
        repo_dir = Path(str(self.get_parameter_value("ltx_repo_dir") or "").strip())
        paths = self._resolve_model_paths()
        checkpoint_path = paths["checkpoint_path"]
        gemma_root = paths["gemma_root"]
        spatial_upsampler_path = paths["spatial_upsampler_path"]
        distilled_lora_path = paths["distilled_lora_path"]
        distilled_lora_strength = float(self.get_parameter_value("distilled_lora_strength") or 0.8)
        prompt = str(self.get_parameter_value("prompt") or "")
        negative_prompt = str(self.get_parameter_value("negative_prompt") or "")
        width = int(self.get_parameter_value("width") or 768)
        height = int(self.get_parameter_value("height") or 512)
        resolution_multiple = self._resolution_multiple_for_pipeline(pipeline_module)
        snapped_width = self._snap_to_multiple(width, resolution_multiple)
        snapped_height = self._snap_to_multiple(height, resolution_multiple)
        num_frames = int(self.get_parameter_value("num_frames") or 121)
        frame_rate = float(self.get_parameter_value("frame_rate") or 25.0)
        num_inference_steps = int(self.get_parameter_value("num_inference_steps") or 40)
        seed = int(self.get_parameter_value("seed") or 42)
        randomize_seed = bool(self.get_parameter_value("randomize_seed") or False)
        if randomize_seed:
            seed = random.SystemRandom().randint(0, 2_147_483_647)
        video_cfg_scale = float(self.get_parameter_value("video_cfg_scale") or 3.0)
        audio_cfg_scale = float(self.get_parameter_value("audio_cfg_scale") or 7.0)
        enhance_prompt = bool(self.get_parameter_value("enhance_prompt") or False)
        extra_cli_args = str(self.get_parameter_value("extra_cli_args") or "").strip()
        image_frame_idx = int(self.get_parameter_value("image_frame_idx") or 0)
        image_strength = float(self.get_parameter_value("image_strength") or 1.0)
        image_crf = int(self.get_parameter_value("image_crf") or 23)
        outpaint_auto_letterbox_to_target = bool(self.get_parameter_value("outpaint_auto_letterbox_to_target") or False)
        video_condition_strength = float(self.get_parameter_value("video_condition_strength") or 1.0)
        conditioning_attention_strength = float(self.get_parameter_value("conditioning_attention_strength") or 1.0)
        outpaint_auto_mask_from_black = bool(self.get_parameter_value("outpaint_auto_mask_from_black") or False)
        outpaint_black_threshold = int(self.get_parameter_value("outpaint_black_threshold") or 8)
        outpaint_min_mask_ratio_warn = float(self.get_parameter_value("outpaint_min_mask_ratio_warn") or 0.05)
        outpaint_mask_white_is_keep = bool(self.get_parameter_value("outpaint_mask_white_is_keep") or False)
        outpaint_strict_preserve_center = bool(self.get_parameter_value("outpaint_strict_preserve_center") or False)
        outpaint_gamma_fix = bool(self.get_parameter_value("outpaint_gamma_fix") or False)
        outpaint_gamma_value = float(self.get_parameter_value("outpaint_gamma_value") or 2.0)
        retake_start_time = float(self.get_parameter_value("retake_start_time") or 0.0)
        retake_end_time = float(self.get_parameter_value("retake_end_time") or 2.0)

        loras = self._parse_lora_stack_json(str(self.get_parameter_value("lora_stack_json") or "[]"))
        self.log_params.append_to_logs(f"Pipeline module: {pipeline_module}\n")
        self.log_params.append_to_logs(f"Runtime LoRAs: {len(loras)}\n")
        self.log_params.append_to_logs(f"Using seed: {seed} (randomize_seed={str(randomize_seed).lower()})\n")
        self.parameter_output_values["used_seed"] = seed
        if snapped_width != width or snapped_height != height:
            self.log_params.append_to_logs(
                f"Adjusted resolution to /{resolution_multiple} multiple: {width}x{height} -> "
                f"{snapped_width}x{snapped_height}\n"
            )
        self.log_params.append_to_logs(f"Resolved checkpoint_path: {checkpoint_path}\n")
        self.log_params.append_to_logs(f"Resolved gemma_root: {gemma_root}\n")
        self.log_params.append_to_logs(f"Resolved spatial_upsampler_path: {spatial_upsampler_path}\n")
        if distilled_lora_path is not None:
            self.log_params.append_to_logs(f"Resolved distilled_lora_path: {distilled_lora_path}\n")

        clip_model_path = str(self.get_parameter_value("clip_model_path") or "").strip()
        vae_model_path = str(self.get_parameter_value("vae_model_path") or "").strip()
        if clip_model_path:
            self.log_params.append_to_logs(
                "Note: clip_model_path provided for compatibility; official ltx_pipelines do not currently use it directly.\n"
            )
        if vae_model_path:
            self.log_params.append_to_logs(
                "Note: vae_model_path provided for compatibility; official ltx_pipelines do not currently use it directly.\n"
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_video_path = Path(tmp_dir) / "ltx_output.mp4"
            input_image_path: Path | None = None
            input_video_path: Path | None = None
            input_mask_video_path: Path | None = None
            preserve_reference_video_path: Path | None = None

            if self.get_parameter_value("input_image"):
                input_image_path = self._artifact_to_temp_media(
                    self.get_parameter_value("input_image"), suffix_default=".png"
                )
                self.log_params.append_to_logs(f"Using input_image: {input_image_path}\n")

            if self.get_parameter_value("input_video"):
                input_video_path = self._artifact_to_temp_media(
                    self.get_parameter_value("input_video"), suffix_default=".mp4"
                )
                self.log_params.append_to_logs(f"Using input_video: {input_video_path}\n")

            if self.get_parameter_value("conditioning_attention_mask_video"):
                input_mask_video_path = self._artifact_to_temp_media(
                    self.get_parameter_value("conditioning_attention_mask_video"), suffix_default=".mp4"
                )
                self.log_params.append_to_logs(f"Using conditioning mask video: {input_mask_video_path}\n")

            if pipeline_module == "ic_lora" and input_video_path is not None:
                if outpaint_auto_letterbox_to_target:
                    letterboxed_input_path = Path(tmp_dir) / "ic_lora_letterboxed_input.mp4"
                    self._letterbox_video_to_target(
                        input_video_path=input_video_path,
                        output_video_path=letterboxed_input_path,
                        target_width=snapped_width,
                        target_height=snapped_height,
                    )
                    input_video_path = letterboxed_input_path
                    preserve_reference_video_path = letterboxed_input_path
                    self.log_params.append_to_logs(
                        f"Applied auto letterbox to target canvas: {snapped_width}x{snapped_height}\n"
                    )
                else:
                    preserve_reference_video_path = input_video_path

                if outpaint_gamma_fix and outpaint_gamma_value > 0:
                    gamma_input_path = Path(tmp_dir) / "ic_lora_gamma_input.mp4"
                    self._apply_gamma_video(input_video_path, gamma_input_path, outpaint_gamma_value)
                    input_video_path = gamma_input_path
                    self.log_params.append_to_logs(
                        f"Applied pre-gamma fix for ic_lora (gamma={outpaint_gamma_value}).\n"
                    )

                if input_mask_video_path is None and outpaint_auto_mask_from_black:
                    auto_mask_path = Path(tmp_dir) / "ic_lora_auto_mask.mp4"
                    mask_ratio = self._build_black_region_mask_video(
                        input_video_path=input_video_path,
                        output_mask_path=auto_mask_path,
                        black_threshold=max(0, min(255, outpaint_black_threshold)),
                        white_is_keep=outpaint_mask_white_is_keep,
                    )
                    input_mask_video_path = auto_mask_path
                    self.log_params.append_to_logs(
                        f"Auto-generated outpaint mask from black regions (threshold={outpaint_black_threshold}, "
                        f"mode={'white=keep' if outpaint_mask_white_is_keep else 'white=generate'}, "
                        f"mean_black_coverage={mask_ratio * 100:.2f}%).\n"
                    )
                    if mask_ratio < max(0.0, min(1.0, outpaint_min_mask_ratio_warn)):
                        self.log_params.append_to_logs(
                            "Warning: auto mask coverage is low. Ensure your input video contains true black outpaint bars.\n"
                        )

            command = [
                python_executable,
                "-m",
                f"ltx_pipelines.{pipeline_module}",
                "--prompt",
                prompt,
                "--output-path",
                str(output_video_path),
                "--seed",
                str(seed),
                "--gemma-root",
                str(gemma_root),
            ]

            if pipeline_module in {"ti2vid_two_stages", "ti2vid_two_stages_hq", "distilled", "ic_lora"}:
                command.extend(
                    [
                        "--height",
                        str(snapped_height),
                        "--width",
                        str(snapped_width),
                        "--num-frames",
                        str(num_frames),
                        "--frame-rate",
                        str(frame_rate),
                        "--spatial-upsampler-path",
                        str(spatial_upsampler_path),
                    ]
                )

            if pipeline_module in {"ti2vid_two_stages", "ti2vid_two_stages_hq"}:
                command.extend(
                    [
                        "--checkpoint-path",
                        str(checkpoint_path),
                        "--negative-prompt",
                        negative_prompt,
                        "--num-inference-steps",
                        str(num_inference_steps),
                        "--video-cfg-guidance-scale",
                        str(video_cfg_scale),
                        "--audio-cfg-guidance-scale",
                        str(audio_cfg_scale),
                        "--distilled-lora",
                        str(distilled_lora_path),
                        str(distilled_lora_strength),
                    ]
                )
            elif pipeline_module in {"distilled", "ic_lora", "retake"}:
                command.extend(
                    [
                        "--distilled-checkpoint-path",
                        str(checkpoint_path),
                    ]
                )

            if pipeline_module == "ic_lora":
                if input_video_path is None:
                    raise ValueError("input_video is required for ic_lora.")
                command.extend(
                    [
                        "--video-conditioning",
                        str(input_video_path),
                        str(video_condition_strength),
                    ]
                )
                if input_mask_video_path is not None:
                    command.extend(
                        [
                            "--conditioning-attention-mask",
                            str(input_mask_video_path),
                            str(conditioning_attention_strength),
                        ]
                    )
            elif pipeline_module == "retake":
                if input_video_path is None:
                    raise ValueError("input_video is required for retake.")
                command.extend(
                    [
                        "--video-path",
                        str(input_video_path),
                        "--start-time",
                        str(retake_start_time),
                        "--end-time",
                        str(retake_end_time),
                    ]
                )
            elif pipeline_module not in {"ti2vid_two_stages", "ti2vid_two_stages_hq", "distilled"}:
                raise ValueError(f"Unsupported pipeline_module: {pipeline_module}")

            if enhance_prompt:
                command.append("--enhance-prompt")

            for lora in loras:
                command.extend(["--lora", lora["path"], str(lora["strength"])])

            if input_image_path is not None and pipeline_module != "retake":
                command.extend(
                    [
                        "--image",
                        str(input_image_path),
                        str(image_frame_idx),
                        str(image_strength),
                        str(image_crf),
                    ]
                )

            if extra_cli_args:
                command.extend(shlex.split(extra_cli_args, posix=False))

            pretty_command = self._command_to_pretty_string(command)
            self.log_params.append_to_logs("Executing command:\n")
            self.log_params.append_to_logs(pretty_command + "\n")
            self.parameter_output_values["debug_command"] = pretty_command

            env = self._build_runtime_env(repo_dir)
            run = subprocess.run(
                command,
                cwd=str(repo_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if run.stdout:
                self.log_params.append_to_logs(run.stdout + "\n")
            if run.stderr:
                self.log_params.append_to_logs(run.stderr + "\n")
            if run.returncode != 0:
                tail_source = run.stderr or run.stdout or ""
                tail_lines = tail_source.strip().splitlines()[-20:]
                tail_text = "\n".join(tail_lines)
                raise ValueError(
                    f"LTX command failed with exit code {run.returncode}."
                    + (f"\nLast output:\n{tail_text}" if tail_text else "")
                )

            if not output_video_path.exists():
                output_video_path = self._find_latest_mp4(Path(tmp_dir))
            if output_video_path is None or not output_video_path.exists():
                raise ValueError("LTX command completed but no output MP4 was found.")

            if pipeline_module == "ic_lora" and outpaint_gamma_fix and outpaint_gamma_value > 0:
                gamma_out_path = Path(tmp_dir) / "ic_lora_gamma_output_restored.mp4"
                self._apply_gamma_video(output_video_path, gamma_out_path, 1.0 / outpaint_gamma_value)
                output_video_path = gamma_out_path
                self.log_params.append_to_logs(
                    f"Applied inverse gamma to output (gamma={1.0 / outpaint_gamma_value:.4f}).\n"
                )

            if pipeline_module == "ic_lora" and outpaint_strict_preserve_center and preserve_reference_video_path is not None:
                composited_path = Path(tmp_dir) / "ic_lora_strict_preserve_center.mp4"
                self._composite_preserve_nonblack_region(
                    reference_video_path=preserve_reference_video_path,
                    generated_video_path=output_video_path,
                    output_video_path=composited_path,
                    black_threshold=max(0, min(255, outpaint_black_threshold)),
                )
                output_video_path = composited_path
                self.log_params.append_to_logs("Applied strict preserve-center composite (non-black region kept from source).\n")

            self.parameter_output_values["output_video"] = self._publish_video(output_video_path)
            self.log_params.append_to_logs(f"LTX-2.3 generation complete: {output_video_path}\n")

    def _parse_lora_stack_json(self, raw: str) -> list[dict[str, Any]]:
        text = raw.strip() or "[]"
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"lora_stack_json is not valid JSON: {e}") from e
        if not isinstance(payload, list):
            raise ValueError("lora_stack_json must be a JSON list.")

        parsed: list[dict[str, Any]] = []
        for idx, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"lora_stack_json item #{idx} must be an object.")
            path = str(item.get("path") or "").strip()
            if not path:
                raise ValueError(f"lora_stack_json item #{idx} is missing 'path'.")
            strength = float(item.get("strength", 1.0))
            if not Path(path).exists():
                raise ValueError(f"LoRA path does not exist: {path}")
            parsed.append({"path": path, "strength": strength})
        return parsed

    def _build_runtime_env(self, repo_dir: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join([str(repo_dir), env.get("PATH", "")])
        return env

    def _resolve_model_paths(self) -> dict[str, Path | None]:
        auto_resolve = bool(self.get_parameter_value("auto_resolve_model_paths") or False)
        models_root_raw = str(self.get_parameter_value("models_root") or "").strip()
        models_root = Path(models_root_raw) if models_root_raw else None
        checkpoint_variant = str(self.get_parameter_value("checkpoint_variant") or "dev").strip().lower()
        upsampler_variant = str(self.get_parameter_value("spatial_upsampler_variant") or "x2").strip().lower()
        pipeline_module = str(self.get_parameter_value("pipeline_module") or "ti2vid_two_stages").strip().lower()

        checkpoint_raw = str(self.get_parameter_value("checkpoint_path") or "").strip()
        gemma_raw = str(self.get_parameter_value("gemma_root") or "").strip()
        upsampler_raw = str(self.get_parameter_value("spatial_upsampler_path") or "").strip()
        distilled_raw = str(self.get_parameter_value("distilled_lora_path") or "").strip()

        checkpoint_path = Path(checkpoint_raw) if checkpoint_raw else None
        gemma_root = Path(gemma_raw) if gemma_raw else None
        spatial_upsampler_path = Path(upsampler_raw) if upsampler_raw else None
        distilled_lora_path = Path(distilled_raw) if distilled_raw else None

        if auto_resolve and models_root is not None:
            checkpoint_is_default = checkpoint_raw in {
                "",
                self.DEFAULT_DEV_CHECKPOINT_PATH,
                self.DEFAULT_DISTILLED_CHECKPOINT_PATH,
            }
            if checkpoint_is_default:
                prefer_distilled = pipeline_module in {"distilled", "ic_lora", "retake"} or checkpoint_variant == "distilled"
                checkpoint_name = self.DEFAULT_DISTILLED_CHECKPOINT if prefer_distilled else self.DEFAULT_DEV_CHECKPOINT
                checkpoint_path = models_root / "checkpoints" / checkpoint_name
            gemma_is_default = gemma_raw in {
                "",
                self.LEGACY_GEMMA_ROOT,
                self.DEFAULT_GEMMA_ROOT,
            }
            if gemma_is_default:
                gemma_root = models_root / "gemma-12b"
            upsampler_is_default = upsampler_raw in {
                "",
                self.DEFAULT_SPATIAL_UPSAMPLER_X2_PATH,
            }
            if upsampler_is_default:
                upsampler_name = self.DEFAULT_SPATIAL_X15 if upsampler_variant == "x1.5" else self.DEFAULT_SPATIAL_X2
                spatial_upsampler_path = models_root / "upscalers" / upsampler_name
            distilled_is_default = distilled_raw in {
                "",
                self.DEFAULT_DISTILLED_LORA_PATH,
            }
            if distilled_is_default:
                distilled_lora_path = models_root / "distilled_lora" / self.DEFAULT_DISTILLED_LORA

        return {
            "checkpoint_path": checkpoint_path,
            "gemma_root": gemma_root,
            "spatial_upsampler_path": spatial_upsampler_path,
            "distilled_lora_path": distilled_lora_path,
        }

    def _publish_video(self, video_path: Path) -> VideoUrlArtifact:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        return VideoUrlArtifact(url)

    def _find_latest_mp4(self, search_root: Path) -> Path | None:
        mp4s = list(search_root.rglob("*.mp4"))
        if not mp4s:
            return None
        mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return mp4s[0]

    def _artifact_value(self, artifact: Any) -> str:
        if artifact is None:
            raise ValueError("Expected media artifact but got None.")
        if isinstance(artifact, str):
            return artifact
        if isinstance(artifact, dict):
            value = artifact.get("value")
            if isinstance(value, str) and value:
                return value
            raise ValueError("Artifact dict is missing 'value'.")
        value = getattr(artifact, "value", None)
        if isinstance(value, str) and value:
            return value
        raise ValueError("Unsupported artifact input type.")

    def _artifact_to_temp_media(self, artifact: Any, suffix_default: str) -> Path:
        source = self._artifact_value(artifact)
        suffix = Path(source).suffix or suffix_default
        fd, temp_path_str = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        Path(temp_path_str).unlink(missing_ok=True)
        out_path = Path(temp_path_str)
        out_path.write_bytes(File(source).read_bytes())
        return out_path

    def _command_to_pretty_string(self, command: list[str]) -> str:
        parts = []
        for part in command:
            part = str(part)
            if " " in part or "\t" in part:
                parts.append(f'"{part}"')
            else:
                parts.append(part)
        return " ".join(parts)

    def _snap_to_multiple(self, value: int, multiple: int) -> int:
        value = max(multiple, int(value))
        snapped = (value // multiple) * multiple
        return max(multiple, snapped)

    def _resolution_multiple_for_pipeline(self, pipeline_module: str) -> int:
        module = (pipeline_module or "").strip().lower()
        if module in {"ti2vid_two_stages", "ti2vid_two_stages_hq", "distilled", "ic_lora"}:
            return 64
        return 32

    def _build_black_region_mask_video(
        self,
        input_video_path: Path,
        output_mask_path: Path,
        black_threshold: int,
        white_is_keep: bool = True,
    ) -> float:
        import imageio.v2 as imageio
        import numpy as np

        reader = imageio.get_reader(str(input_video_path))
        try:
            meta = reader.get_meta_data()
            fps = float(meta.get("fps", 24.0) or 24.0)
            masks: list[np.ndarray] = []
            ratios: list[float] = []
            for frame in reader:
                frame_np = np.asarray(frame)
                if frame_np.ndim == 2:
                    frame_np = np.stack([frame_np, frame_np, frame_np], axis=-1)
                rgb = frame_np[:, :, :3]
                black_region = np.max(rgb, axis=2) <= black_threshold
                ratios.append(float(black_region.mean()))
                if white_is_keep:
                    # Recommended for outpaint: preserve center (non-black), generate bars (black).
                    mask = np.where(black_region, 0, 255).astype(np.uint8)
                else:
                    # Legacy behavior.
                    mask = np.where(black_region, 255, 0).astype(np.uint8)
                mask_rgb = np.stack([mask, mask, mask], axis=-1)
                masks.append(mask_rgb)
        finally:
            reader.close()

        if not masks:
            raise ValueError("Could not build auto outpaint mask: input video has no readable frames.")

        imageio.mimsave(str(output_mask_path), masks, fps=max(1.0, fps))
        return float(sum(ratios) / max(1, len(ratios)))

    def _apply_gamma_video(self, input_video_path: Path, output_video_path: Path, gamma_value: float) -> None:
        import imageio.v2 as imageio
        import numpy as np

        if gamma_value <= 0:
            raise ValueError("Gamma value must be > 0.")

        reader = imageio.get_reader(str(input_video_path))
        try:
            meta = reader.get_meta_data()
            fps = float(meta.get("fps", 24.0) or 24.0)
            out_frames: list[np.ndarray] = []
            inv_gamma = 1.0 / gamma_value
            for frame in reader:
                frame_np = np.asarray(frame).astype(np.float32) / 255.0
                frame_np = np.clip(frame_np, 0.0, 1.0)
                frame_gamma = np.power(frame_np, inv_gamma)
                out = np.uint8(np.clip(frame_gamma * 255.0, 0.0, 255.0))
                out_frames.append(out)
        finally:
            reader.close()

        if not out_frames:
            raise ValueError("Could not apply gamma: input video has no readable frames.")

        imageio.mimsave(str(output_video_path), out_frames, fps=max(1.0, fps))

    def _composite_preserve_nonblack_region(
        self,
        reference_video_path: Path,
        generated_video_path: Path,
        output_video_path: Path,
        black_threshold: int,
    ) -> None:
        import imageio.v2 as imageio
        import numpy as np

        ref_reader = imageio.get_reader(str(reference_video_path))
        gen_reader = imageio.get_reader(str(generated_video_path))
        try:
            meta = gen_reader.get_meta_data()
            fps = float(meta.get("fps", 24.0) or 24.0)
            out_frames: list[np.ndarray] = []
            ref_frames = [np.asarray(f) for f in ref_reader]
            gen_frames = [np.asarray(f) for f in gen_reader]
            frame_count = min(len(ref_frames), len(gen_frames))
            for idx in range(frame_count):
                ref_frame = ref_frames[idx]
                gen_frame = gen_frames[idx]
                if ref_frame.ndim == 2:
                    ref_frame = np.stack([ref_frame, ref_frame, ref_frame], axis=-1)
                if gen_frame.ndim == 2:
                    gen_frame = np.stack([gen_frame, gen_frame, gen_frame], axis=-1)
                h = min(ref_frame.shape[0], gen_frame.shape[0])
                w = min(ref_frame.shape[1], gen_frame.shape[1])
                ref_cut = ref_frame[:h, :w, :3]
                gen_cut = gen_frame[:h, :w, :3]

                black_region = np.max(ref_cut, axis=2) <= black_threshold
                keep_region = np.logical_not(black_region)[:, :, None]
                out = np.where(keep_region, ref_cut, gen_cut).astype(np.uint8)
                out_frames.append(out)
        finally:
            ref_reader.close()
            gen_reader.close()

        if not out_frames:
            raise ValueError("Could not composite preserve-center output: no readable frames.")

        imageio.mimsave(str(output_video_path), out_frames, fps=max(1.0, fps))

    def _letterbox_video_to_target(
        self,
        input_video_path: Path,
        output_video_path: Path,
        target_width: int,
        target_height: int,
    ) -> None:
        import imageio.v2 as imageio
        import numpy as np
        from PIL import Image

        if target_width <= 0 or target_height <= 0:
            raise ValueError("target_width and target_height must be positive for letterboxing.")

        reader = imageio.get_reader(str(input_video_path))
        try:
            meta = reader.get_meta_data()
            fps = float(meta.get("fps", 24.0) or 24.0)
            out_frames: list[np.ndarray] = []
            for frame in reader:
                frame_np = np.asarray(frame)
                if frame_np.ndim == 2:
                    frame_np = np.stack([frame_np, frame_np, frame_np], axis=-1)
                src_h, src_w = frame_np.shape[0], frame_np.shape[1]
                scale = min(target_width / max(src_w, 1), target_height / max(src_h, 1))
                new_w = max(1, int(round(src_w * scale)))
                new_h = max(1, int(round(src_h * scale)))

                resized = np.array(Image.fromarray(frame_np).resize((new_w, new_h), Image.Resampling.BICUBIC))
                canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
                x0 = (target_width - new_w) // 2
                y0 = (target_height - new_h) // 2
                canvas[y0 : y0 + new_h, x0 : x0 + new_w, :] = resized[:, :, :3]
                out_frames.append(canvas)
        finally:
            reader.close()

        if not out_frames:
            raise ValueError("Could not letterbox input video: no readable frames.")

        imageio.mimsave(str(output_video_path), out_frames, fps=max(1.0, fps))
