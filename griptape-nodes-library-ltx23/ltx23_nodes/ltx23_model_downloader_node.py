from __future__ import annotations

from pathlib import Path

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from griptape_nodes.traits.options import Options


class LTX23ModelDownloaderNode(ControlNode):
    """Download LTX-2.3 model assets into a local models folder."""

    CORE_ASSETS = [
        ("Lightricks/LTX-2.3", "ltx-2.3-22b-dev.safetensors", "checkpoints"),
        ("Lightricks/LTX-2.3", "ltx-2.3-22b-distilled.safetensors", "checkpoints"),
        ("Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x2-1.0.safetensors", "upscalers"),
        ("Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x1.5-1.0.safetensors", "upscalers"),
        ("Lightricks/LTX-2.3", "ltx-2.3-temporal-upscaler-x2-1.0.safetensors", "upscalers"),
        ("Lightricks/LTX-2.3", "ltx-2.3-22b-distilled-lora-384.safetensors", "distilled_lora"),
    ]

    EXTRA_LORA_ASSETS = [
        (
            "Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control",
            "ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors",
            "loras/ic",
        ),
        (
            "Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control",
            "ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors",
            "loras/ic",
        ),
        ("Lightricks/LTX-2-19b-IC-LoRA-Detailer", "ltx-2-19b-ic-lora-detailer.safetensors", "loras/ic"),
        ("Lightricks/LTX-2-19b-IC-LoRA-Pose-Control", "ltx-2-19b-ic-lora-pose-control.safetensors", "loras/ic"),
        (
            "Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-In",
            "ltx-2-19b-lora-camera-control-dolly-in.safetensors",
            "loras/camera",
        ),
        (
            "Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Left",
            "ltx-2-19b-lora-camera-control-dolly-left.safetensors",
            "loras/camera",
        ),
        (
            "Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Out",
            "ltx-2-19b-lora-camera-control-dolly-out.safetensors",
            "loras/camera",
        ),
        (
            "Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Right",
            "ltx-2-19b-lora-camera-control-dolly-right.safetensors",
            "loras/camera",
        ),
        (
            "Lightricks/LTX-2-19b-LoRA-Camera-Control-Jib-Down",
            "ltx-2-19b-lora-camera-control-jib-down.safetensors",
            "loras/camera",
        ),
        (
            "Lightricks/LTX-2-19b-LoRA-Camera-Control-Jib-Up",
            "ltx-2-19b-lora-camera-control-jib-up.safetensors",
            "loras/camera",
        ),
        (
            "Lightricks/LTX-2-19b-LoRA-Camera-Control-Static",
            "ltx-2-19b-lora-camera-control-static.safetensors",
            "loras/camera",
        ),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.log_params = LogParameter(self)

        self.add_parameter(
            Parameter(
                name="models_root",
                input_types=["str"],
                type="str",
                default_value=r"A:\GriptapeSketchFab\models\ltx-2.3",
                tooltip="Destination root folder for all downloaded model assets.",
            )
        )
        self.add_parameter(
            Parameter(
                name="download_profile",
                input_types=["str"],
                type="str",
                default_value="all",
                traits={Options(choices=["required", "all"])},
                tooltip="'required' downloads core assets only; 'all' includes extra official LoRAs.",
            )
        )
        self.add_parameter(
            Parameter(
                name="download_gemma_text_encoder",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Also download Gemma text encoder snapshot (very large and may require HF auth).",
            )
        )
        self.add_parameter(
            Parameter(
                name="hf_token",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional Hugging Face token for gated/rate-limited downloads.",
            )
        )
        self.add_parameter(
            Parameter(
                name="force_redownload",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Force refresh even when files already exist.",
            )
        )
        self.add_parameter(
            Parameter(
                name="status",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Download status summary.",
            )
        )
        self.add_parameter(
            Parameter(
                name="downloaded_count",
                output_type="int",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Number of files successfully downloaded.",
            )
        )
        self.add_parameter(
            Parameter(
                name="failed_count",
                output_type="int",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Number of files that failed to download.",
            )
        )
        self.add_parameter(
            Parameter(
                name="models_root_out",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Resolved models root path.",
            )
        )
        self.log_params.add_output_parameters()

    def process(self) -> AsyncResult:
        yield lambda: self._process()

    def _process(self) -> None:
        from huggingface_hub import hf_hub_download, snapshot_download

        self.log_params.clear_logs()
        root = Path(str(self.get_parameter_value("models_root") or "").strip())
        profile = str(self.get_parameter_value("download_profile") or "all").strip().lower()
        download_gemma = bool(self.get_parameter_value("download_gemma_text_encoder") or False)
        force_redownload = bool(self.get_parameter_value("force_redownload") or False)
        hf_token = str(self.get_parameter_value("hf_token") or "").strip() or None

        if not root:
            raise ValueError("models_root is required.")
        root.mkdir(parents=True, exist_ok=True)
        self.log_params.append_to_logs(f"Downloading into: {root}\n")

        assets = list(self.CORE_ASSETS)
        if profile == "all":
            assets.extend(self.EXTRA_LORA_ASSETS)

        downloaded = 0
        failed = 0
        failures: list[str] = []

        for repo_id, filename, subdir in assets:
            local_dir = root / subdir
            local_dir.mkdir(parents=True, exist_ok=True)
            self.log_params.append_to_logs(f"Downloading {repo_id}/{filename} -> {local_dir}\n")
            try:
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=str(local_dir),
                    local_dir_use_symlinks=False,
                    token=hf_token,
                    force_download=force_redownload,
                )
                downloaded += 1
            except Exception as e:
                failed += 1
                failures.append(f"{repo_id}/{filename}: {e}")
                self.log_params.append_to_logs(f"Failed: {repo_id}/{filename} ({e})\n")

        if download_gemma:
            gemma_dir = root / "gemma"
            gemma_dir.mkdir(parents=True, exist_ok=True)
            self.log_params.append_to_logs("Downloading Gemma snapshot (can be very large)...\n")
            try:
                snapshot_download(
                    repo_id="google/gemma-3-12b-it-qat-q4_0-unquantized",
                    local_dir=str(gemma_dir),
                    local_dir_use_symlinks=False,
                    token=hf_token,
                    force_download=force_redownload,
                )
            except Exception as e:
                failed += 1
                failures.append(f"google/gemma-3-12b-it-qat-q4_0-unquantized: {e}")
                self.log_params.append_to_logs(f"Failed Gemma download: {e}\n")

        status = f"Downloaded {downloaded} file(s), failed {failed}."
        if failures:
            status += " See logs for failed assets."
            self.log_params.append_to_logs("\nFailed assets summary:\n")
            for line in failures:
                self.log_params.append_to_logs(f"- {line}\n")

        self.parameter_output_values["status"] = status
        self.parameter_output_values["downloaded_count"] = downloaded
        self.parameter_output_values["failed_count"] = failed
        self.parameter_output_values["models_root_out"] = str(root)
