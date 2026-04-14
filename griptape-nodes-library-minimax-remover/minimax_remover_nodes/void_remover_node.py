from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import numpy as np
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

DEFAULT_VOID_REPO_DIR = r"A:\GriptapeSketchFab\griptape-nodes-library-minimax-remover\void-model"
DEFAULT_VOID_PASS1 = r"A:\GriptapeSketchFab\griptape-nodes-library-minimax-remover\void-model\void_pass1.safetensors"
DEFAULT_VOID_PASS2 = r"A:\GriptapeSketchFab\griptape-nodes-library-minimax-remover\void-model\void_pass2.safetensors"
DEFAULT_COGVIDEOX_DIR = r"A:\GriptapeSketchFab\griptape-nodes-library-minimax-remover\void-model\CogVideoX-Fun-V1.5-5b-InP"
DEFAULT_PYTHON_EXE = r"C:\Users\AI PC\AppData\Local\Programs\Python\Python310\python.exe"


class VoidRemoverNode(ControlNode):
    """High-end video object removal node using Netflix VOID CLI."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.log_params = LogParameter(self)

        self.add_parameter(
            Parameter(
                name="input_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Source video to process.",
            )
        )
        self.add_parameter(
            Parameter(
                name="input_mask_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Binary mask video (white=remove, black=keep). Converted to quadmask automatically.",
            )
        )
        self.add_parameter(
            Parameter(
                name="input_affected_mask_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Optional affected-region mask video (white=affected interactions). Used for richer 4-value quadmask.",
            )
        )
        self.add_parameter(
            Parameter(
                name="background_prompt",
                input_types=["str"],
                type="str",
                default_value="clean background after object removal",
                tooltip="Prompt describing the scene after removal (used in prompt.json).",
            )
        )
        self.add_parameter(
            Parameter(
                name="void_repo_dir",
                input_types=["str"],
                type="str",
                default_value=DEFAULT_VOID_REPO_DIR,
                tooltip="Local path to cloned VOID repository root.",
            )
        )
        self.add_parameter(
            Parameter(
                name="void_pass1_checkpoint",
                input_types=["str"],
                type="str",
                default_value=DEFAULT_VOID_PASS1,
                tooltip="Path to void_pass1.safetensors checkpoint.",
            )
        )
        self.add_parameter(
            Parameter(
                name="cogvideox_model_dir",
                input_types=["str"],
                type="str",
                default_value=DEFAULT_COGVIDEOX_DIR,
                tooltip="Path to base model directory (CogVideoX-Fun-V1.5-5b-InP). Relative paths resolve from void_repo_dir.",
            )
        )
        self.add_parameter(
            Parameter(
                name="enable_pass2_refinement",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Enable optional VOID pass-2 temporal refinement.",
            )
        )
        self.add_parameter(
            Parameter(
                name="void_pass2_checkpoint",
                input_types=["str"],
                type="str",
                default_value=DEFAULT_VOID_PASS2,
                tooltip="Path to void_pass2.safetensors checkpoint (required when pass2 is enabled).",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass2_auto_for_long_clips",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="If true, pass2 runs only when clip length is >= pass2_min_frames.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass2_min_frames",
                input_types=["int"],
                type="int",
                default_value=240,
                tooltip="Frame threshold used when pass2_auto_for_long_clips is enabled.",
            )
        )
        self.add_parameter(
            Parameter(
                name="config_path",
                input_types=["str"],
                type="str",
                default_value="config/quadmask_cogvideox.py",
                tooltip="Config path relative to void_repo_dir (or absolute).",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_height",
                input_types=["int"],
                type="int",
                default_value=0,
                tooltip="Output height override. Use 0 to keep VOID config default.",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_width",
                input_types=["int"],
                type="int",
                default_value=0,
                tooltip="Output width override. Use 0 to keep VOID config default.",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_fps",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Output FPS override. Use 0 to preserve source FPS.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass1_num_inference_steps",
                input_types=["int"],
                type="int",
                default_value=50,
                tooltip="VOID pass1 denoising steps.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass1_temporal_window_size",
                input_types=["int"],
                type="int",
                default_value=85,
                tooltip="VOID pass1 temporal window size.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass1_max_video_length",
                input_types=["int"],
                type="int",
                default_value=197,
                tooltip="VOID pass1 max frames. Use 0 to keep config default.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass1_guidance_scale",
                input_types=["float"],
                type="float",
                default_value=1.0,
                tooltip="VOID pass1 guidance scale.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass2_num_inference_steps",
                input_types=["int"],
                type="int",
                default_value=50,
                tooltip="VOID pass2 denoising steps.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass2_temporal_window_size",
                input_types=["int"],
                type="int",
                default_value=85,
                tooltip="VOID pass2 temporal window size.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass2_guidance_scale",
                input_types=["float"],
                type="float",
                default_value=6.0,
                tooltip="VOID pass2 guidance scale.",
            )
        )
        self.add_parameter(
            Parameter(
                name="python_executable",
                input_types=["str"],
                type="str",
                default_value=DEFAULT_PYTHON_EXE,
                tooltip="Python executable for running VOID inference.",
            )
        )
        self.add_parameter(
            Parameter(
                name="extra_cli_args",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional extra CLI args appended to VOID pass-1 command.",
            )
        )
        self.add_parameter(
            Parameter(
                name="pass2_extra_cli_args",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional extra CLI args appended to VOID pass-2 command.",
            )
        )
        self.add_parameter(
            Parameter(
                name="mask_threshold",
                input_types=["int"],
                type="int",
                default_value=20,
                tooltip="Threshold for converting binary mask frames into quadmask remove/keep regions.",
            )
        )
        self.add_parameter(
            Parameter(
                name="affected_mask_threshold",
                input_types=["int"],
                type="int",
                default_value=20,
                tooltip="Threshold for affected-region mask video when building rich quadmask.",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="VOID processed output video.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_quadmask_video",
                output_type="VideoUrlArtifact",
                tooltip="Generated quadmask video used as VOID input.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_preview_tuple_video",
                output_type="VideoUrlArtifact",
                tooltip="Optional VOID side-by-side preview tuple video.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.log_params.add_output_parameters()

    def validate_before_node_run(self) -> list[Exception] | None:
        errors: list[Exception] = []

        if not self.get_parameter_value("input_video"):
            errors.append(ValueError("input_video is required."))
        if not self.get_parameter_value("input_mask_video"):
            errors.append(ValueError("input_mask_video is required."))

        repo_dir = str(self.get_parameter_value("void_repo_dir") or "").strip()
        if not repo_dir:
            errors.append(ValueError("void_repo_dir is required and must point to a local VOID repo checkout."))
        else:
            repo_path = Path(repo_dir)
            if not repo_path.exists():
                errors.append(ValueError(f"void_repo_dir does not exist: {repo_path}"))
            elif not (repo_path / "inference" / "cogvideox_fun" / "predict_v2v.py").exists():
                errors.append(
                    ValueError("void_repo_dir does not look valid (missing inference/cogvideox_fun/predict_v2v.py).")
                )

        ckpt = str(self.get_parameter_value("void_pass1_checkpoint") or "").strip()
        if not ckpt:
            errors.append(ValueError("void_pass1_checkpoint is required."))
        elif not Path(ckpt).exists():
            errors.append(ValueError(f"void_pass1_checkpoint does not exist: {ckpt}"))

        model_dir_value = str(self.get_parameter_value("cogvideox_model_dir") or "").strip()
        if not model_dir_value:
            errors.append(ValueError("cogvideox_model_dir is required."))
        elif repo_dir:
            model_dir_path = Path(model_dir_value)
            if not model_dir_path.is_absolute():
                model_dir_path = Path(repo_dir) / model_dir_path
            if not model_dir_path.exists():
                errors.append(ValueError(f"cogvideox_model_dir does not exist: {model_dir_path}"))

        enable_pass2 = bool(self.get_parameter_value("enable_pass2_refinement") or False)
        pass2_ckpt = str(self.get_parameter_value("void_pass2_checkpoint") or "").strip()
        if enable_pass2:
            if not pass2_ckpt:
                errors.append(ValueError("void_pass2_checkpoint is required when enable_pass2_refinement is true."))
            elif not Path(pass2_ckpt).exists():
                errors.append(ValueError(f"void_pass2_checkpoint does not exist: {pass2_ckpt}"))

        return errors or None

    def process(self) -> AsyncResult:
        yield lambda: self._process()

    def _process(self) -> None:
        self.log_params.clear_logs()
        self.log_params.append_to_logs("VOID remover: preparing inputs...\n")

        python_exe = str(self.get_parameter_value("python_executable") or "python").strip() or "python"
        repo_dir = Path(str(self.get_parameter_value("void_repo_dir") or "").strip())
        ckpt_pass1 = Path(str(self.get_parameter_value("void_pass1_checkpoint") or "").strip())
        enable_pass2 = bool(self.get_parameter_value("enable_pass2_refinement") or False)
        ckpt_pass2 = Path(str(self.get_parameter_value("void_pass2_checkpoint") or "").strip())
        model_dir_value = str(self.get_parameter_value("cogvideox_model_dir") or "CogVideoX-Fun-V1.5-5b-InP").strip()
        model_dir_path = Path(model_dir_value)
        if not model_dir_path.is_absolute():
            model_dir_path = repo_dir / model_dir_path
        config_value = str(self.get_parameter_value("config_path") or "config/quadmask_cogvideox.py").strip()
        config_path = Path(config_value) if Path(config_value).is_absolute() else (repo_dir / config_value)
        output_height = max(0, int(self.get_parameter_value("output_height") or 0))
        output_width = max(0, int(self.get_parameter_value("output_width") or 0))
        output_fps = float(self.get_parameter_value("output_fps") or 0.0)
        pass1_steps = max(1, int(self.get_parameter_value("pass1_num_inference_steps") or 50))
        pass1_window = max(1, int(self.get_parameter_value("pass1_temporal_window_size") or 85))
        pass1_max_len = max(0, int(self.get_parameter_value("pass1_max_video_length") or 197))
        pass1_guidance = float(self.get_parameter_value("pass1_guidance_scale") or 1.0)
        pass2_steps = max(1, int(self.get_parameter_value("pass2_num_inference_steps") or 50))
        pass2_window = max(1, int(self.get_parameter_value("pass2_temporal_window_size") or 85))
        pass2_guidance = float(self.get_parameter_value("pass2_guidance_scale") or 6.0)
        pass1_extra_cli_args = str(self.get_parameter_value("extra_cli_args") or "").strip()
        pass2_extra_cli_args = str(self.get_parameter_value("pass2_extra_cli_args") or "").strip()
        bg_prompt = str(self.get_parameter_value("background_prompt") or "").strip()
        threshold = int(self.get_parameter_value("mask_threshold") or 20)
        affected_threshold = int(self.get_parameter_value("affected_mask_threshold") or 20)
        affected_mask_artifact = self.get_parameter_value("input_affected_mask_video")
        pass2_auto_for_long = bool(self.get_parameter_value("pass2_auto_for_long_clips") or False)
        pass2_min_frames = max(1, int(self.get_parameter_value("pass2_min_frames") or 240))

        if not config_path.exists():
            raise ValueError(f"config_path does not exist: {config_path}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_root = root / "void_data"
            seq_name = "job0"
            seq_dir = data_root / seq_name
            save_root = root / "void_outputs"
            seq_dir.mkdir(parents=True, exist_ok=True)
            save_root.mkdir(parents=True, exist_ok=True)

            input_video_path = seq_dir / "input_video.mp4"
            binary_mask_path = root / "binary_mask.mp4"
            quadmask_path = seq_dir / "quadmask_0.mp4"
            prompt_path = seq_dir / "prompt.json"

            input_video_path.write_bytes(File(self._artifact_value(self.get_parameter_value("input_video"))).read_bytes())
            binary_mask_path.write_bytes(File(self._artifact_value(self.get_parameter_value("input_mask_video"))).read_bytes())
            source_fps = self._detect_video_fps(input_video_path, default_fps=12.0)
            effective_fps = output_fps if output_fps > 0 else source_fps
            effective_fps_int = max(1, int(round(effective_fps)))
            affected_mask_path: Path | None = None
            if affected_mask_artifact:
                affected_mask_path = root / "affected_mask.mp4"
                affected_mask_path.write_bytes(File(self._artifact_value(affected_mask_artifact)).read_bytes())

            self.log_params.append_to_logs("Converting binary mask to VOID quadmask...\n")
            frame_count = self._build_quadmask_video(
                primary_mask_video=binary_mask_path,
                output_quadmask_video=quadmask_path,
                primary_threshold=threshold,
                affected_mask_video=affected_mask_path,
                affected_threshold=affected_threshold,
            )
            self.log_params.append_to_logs(f"Prepared quadmask for {frame_count} frames.\n")

            with prompt_path.open("w", encoding="utf-8") as f:
                json.dump({"bg": bg_prompt or "clean background after object removal"}, f)

            self._run_void_command(
                python_exe=python_exe,
                repo_dir=repo_dir,
                config_path=config_path,
                data_root=data_root,
                seq_name=seq_name,
                save_root=save_root,
                model_name_path=model_dir_path,
                checkpoint_path=ckpt_pass1,
                extra_cli_args=pass1_extra_cli_args,
                output_height=output_height,
                output_width=output_width,
                output_fps=effective_fps_int,
                pass1_steps=pass1_steps,
                pass1_window=pass1_window,
                pass1_max_len=pass1_max_len,
                pass1_guidance=pass1_guidance,
                stage_name="pass1",
            )

            output_video_path, tuple_video_path = self._find_void_outputs(save_root, seq_name=seq_name)
            if output_video_path is None:
                raise ValueError("VOID pass1 completed but no output MP4 was found.")

            should_run_pass2 = enable_pass2 and ((not pass2_auto_for_long) or (frame_count >= pass2_min_frames))
            if enable_pass2 and pass2_auto_for_long and not should_run_pass2:
                self.log_params.append_to_logs(
                    f"Skipping pass2: frame_count={frame_count} is below pass2_min_frames={pass2_min_frames}.\n"
                )
            if should_run_pass2:
                self.log_params.append_to_logs("VOID remover: running optional pass2 refinement...\n")
                save_root_p2 = root / "void_outputs_pass2"
                save_root_p2.mkdir(parents=True, exist_ok=True)
                # VOID pass2 helper searches pass1_dir with pattern:
                #   {video_name}-fg=-1-*.mp4
                # Our pass1 output can be {video_name}.mp4, so create a compatible alias.
                pass1_alias = save_root / f"{seq_name}-fg=-1-auto.mp4"
                if output_video_path is not None and output_video_path.exists():
                    try:
                        shutil.copy2(output_video_path, pass1_alias)
                        self.log_params.append_to_logs(f"Prepared pass1 alias for pass2: {pass1_alias.name}\n")
                    except Exception as e:
                        self.log_params.append_to_logs(f"Warning: could not create pass1 alias ({e}).\n")
                self._run_void_pass2_command(
                    python_exe=python_exe,
                    repo_dir=repo_dir,
                    data_root=data_root,
                    seq_name=seq_name,
                    pass1_dir=save_root,
                    output_dir=save_root_p2,
                    model_name_path=model_dir_path,
                    checkpoint_path=ckpt_pass2,
                    extra_cli_args=pass2_extra_cli_args,
                    pass2_steps=pass2_steps,
                    pass2_window=pass2_window,
                    pass2_guidance=pass2_guidance,
                )
                pass2_video_path, pass2_tuple_path = self._find_void_outputs(save_root_p2, seq_name=seq_name)
                if pass2_video_path is None:
                    self.log_params.append_to_logs(
                        "Warning: pass2 completed but no output MP4 was found. Falling back to pass1 output.\n"
                    )
                else:
                    output_video_path = pass2_video_path
                    tuple_video_path = pass2_tuple_path

            output_video_path = self._rewrite_video_fps_if_needed(
                input_video_path=output_video_path,
                output_path=(root / "void_final_fps.mp4"),
                fps=effective_fps_int,
            )
            output_video_path = self._extract_inpaint_from_tuple_if_needed(
                input_video_path=output_video_path,
                output_path=(root / "void_final_clean.mp4"),
                fps=effective_fps_int,
            )
            self.parameter_output_values["output_video"] = self._publish_video(output_video_path)
            self.parameter_output_values["output_quadmask_video"] = self._publish_video(quadmask_path)
            self.parameter_output_values["output_preview_tuple_video"] = (
                self._publish_video(tuple_video_path) if tuple_video_path is not None else None
            )
            self.log_params.append_to_logs(f"VOID remover: done. Output={output_video_path}\n")

    def _run_void_command(
        self,
        python_exe: str,
        repo_dir: Path,
        config_path: Path,
        data_root: Path,
        seq_name: str,
        save_root: Path,
        model_name_path: Path,
        checkpoint_path: Path,
        extra_cli_args: str,
        output_height: int,
        output_width: int,
        output_fps: float,
        pass1_steps: int,
        pass1_window: int,
        pass1_max_len: int,
        pass1_guidance: float,
        stage_name: str,
    ) -> None:
        config_cli = self._path_for_cli(config_path, repo_dir)
        data_root_cli = self._path_for_cli(data_root, repo_dir)
        save_root_cli = self._path_for_cli(save_root, repo_dir)
        model_name_cli = self._path_for_cli(model_name_path, repo_dir)
        checkpoint_cli = self._path_for_cli(checkpoint_path, repo_dir)

        command = [
            python_exe,
            str(repo_dir / "inference" / "cogvideox_fun" / "predict_v2v.py"),
            "--config",
            config_cli,
            f"--config.data.data_rootdir={data_root_cli}",
            f"--config.experiment.run_seqs={seq_name}",
            f"--config.experiment.save_path={save_root_cli}",
            f"--config.video_model.model_name={model_name_cli}",
            f"--config.video_model.transformer_path={checkpoint_cli}",
        ]
        if output_height > 0 and output_width > 0:
            snapped_height = self._snap_down_to_multiple(output_height, 8)
            snapped_width = self._snap_down_to_multiple(output_width, 8)
            if snapped_height != output_height or snapped_width != output_width:
                self.log_params.append_to_logs(
                    f"Adjusted sample_size to /8 multiple: {output_height}x{output_width} -> "
                    f"{snapped_height}x{snapped_width}\n"
                )
            command.append(f"--config.data.sample_size={snapped_height}x{snapped_width}")
        if output_fps > 0:
            command.append(f"--config.data.fps={output_fps}")
        command.append(f"--config.video_model.num_inference_steps={pass1_steps}")
        command.append(f"--config.video_model.temporal_window_size={pass1_window}")
        command.append(f"--config.video_model.guidance_scale={pass1_guidance}")
        if pass1_max_len > 0:
            command.append(f"--config.data.max_video_length={pass1_max_len}")
        if extra_cli_args:
            command.extend(extra_cli_args.split())

        self.log_params.append_to_logs(f"Running VOID {stage_name} command in {repo_dir}\n")
        self.log_params.append_to_logs(" ".join(command) + "\n")

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
                f"VOID {stage_name} inference failed with exit code {run.returncode}."
                + (f"\nLast output:\n{tail_text}" if tail_text else "")
            )

    def _run_void_pass2_command(
        self,
        python_exe: str,
        repo_dir: Path,
        data_root: Path,
        seq_name: str,
        pass1_dir: Path,
        output_dir: Path,
        model_name_path: Path,
        checkpoint_path: Path,
        extra_cli_args: str,
        pass2_steps: int,
        pass2_window: int,
        pass2_guidance: float,
    ) -> None:
        data_root_cli = self._path_for_cli(data_root, repo_dir)
        pass1_dir_cli = self._path_for_cli(pass1_dir, repo_dir)
        output_dir_cli = self._path_for_cli(output_dir, repo_dir)
        model_name_cli = self._path_for_cli(model_name_path, repo_dir)
        checkpoint_cli = self._path_for_cli(checkpoint_path, repo_dir)

        command = [
            python_exe,
            str(repo_dir / "inference" / "cogvideox_fun" / "inference_with_pass1_warped_noise.py"),
            "--video_name",
            seq_name,
            "--data_rootdir",
            data_root_cli,
            "--pass1_dir",
            pass1_dir_cli,
            "--output_dir",
            output_dir_cli,
            "--model_checkpoint",
            checkpoint_cli,
            "--model_name",
            model_name_cli,
            "--num_inference_steps",
            str(pass2_steps),
            "--guidance_scale",
            str(pass2_guidance),
            "--temporal_window_size",
            str(pass2_window),
        ]
        if extra_cli_args:
            command.extend(extra_cli_args.split())

        self.log_params.append_to_logs(f"Running VOID pass2 command in {repo_dir}\n")
        self.log_params.append_to_logs(" ".join(command) + "\n")

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
                f"VOID pass2 inference failed with exit code {run.returncode}."
                + (f"\nLast output:\n{tail_text}" if tail_text else "")
            )

    def _build_runtime_env(self, repo_dir: Path) -> dict[str, str]:
        env = os.environ.copy()
        path_sep = os.pathsep
        path_entries = [str(repo_dir), env.get("PATH", "")]

        # Ensure ffmpeg is available for mediapy/video decoding.
        ffmpeg_repo_path = repo_dir / "ffmpeg.exe"
        try:
            import imageio_ffmpeg

            ffmpeg_imageio = Path(imageio_ffmpeg.get_ffmpeg_exe())
            env["IMAGEIO_FFMPEG_EXE"] = str(ffmpeg_imageio)
            path_entries.insert(0, str(ffmpeg_imageio.parent))
            if not ffmpeg_repo_path.exists():
                shutil.copy2(ffmpeg_imageio, ffmpeg_repo_path)
        except Exception:
            pass

        env["PATH"] = path_sep.join([p for p in path_entries if p])
        return env

    def _path_for_cli(self, path: Path, repo_dir: Path) -> str:
        """Prefer relative POSIX-style paths to avoid Windows drive-letter parsing issues."""
        try:
            path_resolved = path.resolve()
            repo_resolved = repo_dir.resolve()
            rel = path_resolved.relative_to(repo_resolved)
            return rel.as_posix()
        except Exception:
            return str(path).replace("\\", "/")

    def _artifact_value(self, artifact: Any) -> str:
        if artifact is None:
            raise ValueError("Expected video artifact but got None.")
        if isinstance(artifact, str):
            return artifact
        if isinstance(artifact, dict):
            value = artifact.get("value")
            if isinstance(value, str) and value:
                return value
            raise ValueError("Video artifact dict is missing 'value'.")
        value = getattr(artifact, "value", None)
        if isinstance(value, str) and value:
            return value
        raise ValueError("Unsupported video artifact input type.")

    def _build_quadmask_video(
        self,
        primary_mask_video: Path,
        output_quadmask_video: Path,
        primary_threshold: int = 20,
        affected_mask_video: Path | None = None,
        affected_threshold: int = 20,
    ) -> int:
        primary_reader = imageio.get_reader(str(primary_mask_video))
        affected_reader = imageio.get_reader(str(affected_mask_video)) if affected_mask_video is not None else None
        try:
            meta = primary_reader.get_meta_data()
            fps = float(meta.get("fps", 24.0) or 24.0)
            frames: list[np.ndarray] = []
            affected_frames: list[np.ndarray] | None = None
            if affected_reader is not None:
                affected_frames = [np.asarray(frame) for frame in affected_reader]

            for idx, frame in enumerate(primary_reader):
                primary_np = np.asarray(frame)
                if primary_np.ndim == 2:
                    primary_gray = primary_np
                else:
                    primary_gray = primary_np[:, :, 0]
                primary_region = primary_gray > primary_threshold

                if affected_frames is not None and idx < len(affected_frames):
                    affected_np = affected_frames[idx]
                    if affected_np.ndim == 2:
                        affected_gray = affected_np
                    else:
                        affected_gray = affected_np[:, :, 0]

                    # Align safely when mask videos differ in dimensions.
                    h = min(primary_region.shape[0], affected_gray.shape[0])
                    w = min(primary_region.shape[1], affected_gray.shape[1])
                    primary_cut = primary_region[:h, :w]
                    affected_cut = (affected_gray[:h, :w] > affected_threshold)

                    quad = np.full((h, w), 255, dtype=np.uint8)
                    quad[np.logical_and(affected_cut, np.logical_not(primary_cut))] = 127
                    quad[np.logical_and(primary_cut, affected_cut)] = 63
                    quad[np.logical_and(primary_cut, np.logical_not(affected_cut))] = 0
                else:
                    quad = np.where(primary_region, 0, 255).astype(np.uint8)

                quad_rgb = np.stack([quad, quad, quad], axis=-1)
                frames.append(quad_rgb)
        finally:
            primary_reader.close()
            if affected_reader is not None:
                affected_reader.close()

        if not frames:
            raise ValueError("Binary mask video has no readable frames.")
        imageio.mimsave(str(output_quadmask_video), frames, fps=max(1.0, fps))
        return len(frames)

    def _find_latest_mp4(self, search_root: Path) -> Path | None:
        mp4s = list(search_root.rglob("*.mp4"))
        if not mp4s:
            return None
        mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return mp4s[0]

    def _find_void_outputs(self, search_root: Path, seq_name: str) -> tuple[Path | None, Path | None]:
        """Pick main inpaint output and optional tuple preview video."""
        mp4s = list(search_root.rglob("*.mp4"))
        if not mp4s:
            return None, None

        tuple_candidates = [p for p in mp4s if p.stem.endswith("_tuple")]
        tuple_video = None
        exact_tuple = [p for p in tuple_candidates if p.stem == f"{seq_name}_tuple"]
        if exact_tuple:
            tuple_video = exact_tuple[0]
        elif tuple_candidates:
            tuple_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            tuple_video = tuple_candidates[0]

        exact_main = [p for p in mp4s if p.stem == seq_name]
        if exact_main:
            return exact_main[0], tuple_video

        non_tuple = [p for p in mp4s if not p.stem.endswith("_tuple")]
        if non_tuple:
            non_tuple.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return non_tuple[0], tuple_video

        mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return mp4s[0], tuple_video

    def _publish_video(self, video_path: Path) -> VideoUrlArtifact:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        return VideoUrlArtifact(url)

    def _detect_video_fps(self, video_path: Path, default_fps: float = 12.0) -> float:
        reader = imageio.get_reader(str(video_path))
        try:
            meta = reader.get_meta_data()
            fps = float(meta.get("fps", default_fps) or default_fps)
            return fps if fps > 0 else default_fps
        except Exception:
            return default_fps
        finally:
            reader.close()

    def _rewrite_video_fps_if_needed(self, input_video_path: Path, output_path: Path, fps: float) -> Path:
        if fps <= 0:
            return input_video_path
        try:
            reader = imageio.get_reader(str(input_video_path))
            try:
                frames = [np.asarray(frame) for frame in reader]
            finally:
                reader.close()
            if not frames:
                return input_video_path
            imageio.mimsave(str(output_path), frames, fps=max(1.0, fps))
            return output_path
        except Exception:
            return input_video_path

    def _extract_inpaint_from_tuple_if_needed(self, input_video_path: Path, output_path: Path, fps: float) -> Path:
        """If input looks like VOID 4-panel tuple, extract panel #3 (inpaint result)."""
        try:
            reader = imageio.get_reader(str(input_video_path))
            try:
                frames = [np.asarray(frame) for frame in reader]
            finally:
                reader.close()
            if not frames:
                return input_video_path

            first = frames[0]
            if first.ndim != 3:
                return input_video_path
            h, w = first.shape[0], first.shape[1]
            looks_like_tuple = (w % 4 == 0 and (w / max(h, 1)) >= 2.8) or input_video_path.stem.endswith("_tuple")
            if not looks_like_tuple:
                return input_video_path

            panel_w = w // 4
            start_x = panel_w * 2
            end_x = panel_w * 3
            cropped_frames = [frame[:, start_x:end_x, :] for frame in frames]
            imageio.mimsave(str(output_path), cropped_frames, fps=max(1.0, fps))
            self.log_params.append_to_logs("Detected tuple output and extracted clean inpaint panel for output_video.\n")
            return output_path
        except Exception:
            return input_video_path

    def _snap_down_to_multiple(self, value: int, multiple: int) -> int:
        if value <= 0:
            return 0
        value_i = int(value)
        snapped = (value_i // multiple) * multiple
        return max(multiple, snapped)

