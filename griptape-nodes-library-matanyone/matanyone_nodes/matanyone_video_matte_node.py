from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from huggingface_hub import snapshot_download  # type: ignore[reportMissingImports]
from matanyone import InferenceCore  # type: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


class MatAnyoneVideoMatteNode(DataNode):
    """Run MatAnyone video matting with hardwired model setup."""

    MODEL_REPO_ID = "PeiqingYang/MatAnyone"

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "VideoMatting",
            "description": "Stable video matting with MatAnyone and auto model download.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="input_video_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Input video path (.mp4/.mov/.avi) or input frame-folder path.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="input_mask_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="First-frame target segmentation mask path.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_directory",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional output folder. Defaults to <video_parent>/matanyone_results.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_suffix",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional suffix appended to output names.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="n_warmup",
                input_types=["int"],
                type="int",
                default_value=10,
                tooltip="Warmup frame count for stable propagation.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="r_erode",
                input_types=["int"],
                type="int",
                default_value=10,
                tooltip="Erode radius on initial mask.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="r_dilate",
                input_types=["int"],
                type="int",
                default_value=10,
                tooltip="Dilate radius on initial mask.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="max_size",
                input_types=["int"],
                type="int",
                default_value=-1,
                tooltip="Maximum input size; set -1 to disable resizing.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="save_image",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Save per-frame image outputs in addition to videos.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="foreground_video_path",
                output_type="str",
                tooltip="Output foreground video path.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="alpha_video_path",
                output_type="str",
                tooltip="Output alpha video path.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="model_cache_path",
                output_type="str",
                tooltip="Resolved local cache directory for the hardwired MatAnyone model.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status_message",
                output_type="str",
                tooltip="Execution status.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    @staticmethod
    def _safe_str(value: Any) -> str:
        return str(value or "").strip()

    def process(self) -> None:
        video_path_text = self._safe_str(self.parameter_values.get("input_video_path", ""))
        mask_path_text = self._safe_str(self.parameter_values.get("input_mask_path", ""))
        output_dir_text = self._safe_str(self.parameter_values.get("output_directory", ""))
        output_suffix = self._safe_str(self.parameter_values.get("output_suffix", ""))

        if not video_path_text:
            self.parameter_output_values["status_message"] = "input_video_path is required."
            self.parameter_output_values["foreground_video_path"] = ""
            self.parameter_output_values["alpha_video_path"] = ""
            self.parameter_output_values["model_cache_path"] = ""
            return

        if not mask_path_text:
            self.parameter_output_values["status_message"] = "input_mask_path is required."
            self.parameter_output_values["foreground_video_path"] = ""
            self.parameter_output_values["alpha_video_path"] = ""
            self.parameter_output_values["model_cache_path"] = ""
            return

        video_path = Path(video_path_text)
        mask_path = Path(mask_path_text)
        if not video_path.exists():
            self.parameter_output_values["status_message"] = f"Input video path not found: {video_path}"
            self.parameter_output_values["foreground_video_path"] = ""
            self.parameter_output_values["alpha_video_path"] = ""
            self.parameter_output_values["model_cache_path"] = ""
            return
        if not mask_path.exists():
            self.parameter_output_values["status_message"] = f"Input mask path not found: {mask_path}"
            self.parameter_output_values["foreground_video_path"] = ""
            self.parameter_output_values["alpha_video_path"] = ""
            self.parameter_output_values["model_cache_path"] = ""
            return

        output_dir = Path(output_dir_text) if output_dir_text else video_path.parent / "matanyone_results"
        output_dir.mkdir(parents=True, exist_ok=True)

        n_warmup = int(self.parameter_values.get("n_warmup", 10))
        r_erode = int(self.parameter_values.get("r_erode", 10))
        r_dilate = int(self.parameter_values.get("r_dilate", 10))
        max_size = int(self.parameter_values.get("max_size", -1))
        save_image = bool(self.parameter_values.get("save_image", False))

        try:
            # Force download/cache resolution up-front so the node reports the exact model location.
            model_cache_path = snapshot_download(repo_id=self.MODEL_REPO_ID)
            logger.info("MatAnyone model cache resolved at %s", model_cache_path)

            processor = InferenceCore(self.MODEL_REPO_ID)
            foreground_path, alpha_path = processor.process_video(
                input_path=str(video_path),
                mask_path=str(mask_path),
                output_path=str(output_dir),
                n_warmup=n_warmup,
                r_erode=r_erode,
                r_dilate=r_dilate,
                suffix=output_suffix,
                save_image=save_image,
                max_size=max_size,
            )

            foreground_out = self._safe_str(foreground_path)
            alpha_out = self._safe_str(alpha_path)
            status = "MatAnyone complete. Model is hardwired and auto-downloaded."
            logger.info(status)

            self.parameter_output_values["foreground_video_path"] = foreground_out
            self.parameter_output_values["alpha_video_path"] = alpha_out
            self.parameter_output_values["model_cache_path"] = self._safe_str(model_cache_path)
            self.parameter_output_values["status_message"] = status
        except Exception as exc:
            error_status = f"MatAnyone processing failed: {exc}"
            logger.exception(error_status)
            self.parameter_output_values["foreground_video_path"] = ""
            self.parameter_output_values["alpha_video_path"] = ""
            self.parameter_output_values["model_cache_path"] = ""
            self.parameter_output_values["status_message"] = error_status
