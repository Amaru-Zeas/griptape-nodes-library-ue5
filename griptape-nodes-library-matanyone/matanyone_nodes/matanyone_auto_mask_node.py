from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2  # type: ignore[reportMissingImports]
import numpy as np
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from huggingface_hub import hf_hub_download, snapshot_download  # type: ignore[reportMissingImports]
from sam2.build_sam import HF_MODEL_ID_TO_FILENAMES, build_sam2  # type: ignore[reportMissingImports]
from sam2.sam2_image_predictor import SAM2ImagePredictor  # type: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


class MatAnyoneAutoMaskNode(DataNode):
    """Generate first-frame mask for MatAnyone using hardwired SAM2 model."""

    SAM2_REPO_ID = "facebook/sam2-hiera-large"

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "VideoMatting",
            "description": "Create first-frame segmentation mask via hardwired SAM2.",
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
                tooltip="Input video path (.mp4/.mov/.avi).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_mask_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional output mask path. Defaults to <video_parent>/<video_stem>_mask.png.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="save_first_frame",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Save extracted first frame image for reference.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="positive_point_x_ratio",
                input_types=["float"],
                type="float",
                default_value=0.5,
                tooltip="Center-X ratio for default positive prompt point (0..1).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="positive_point_y_ratio",
                input_types=["float"],
                type="float",
                default_value=0.5,
                tooltip="Center-Y ratio for default positive prompt point (0..1).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="mask_threshold",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="SAM2 mask threshold when converting logits to binary mask.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="multimask_output",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Generate multiple candidates and keep highest-score mask.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_mask_path_out",
                output_type="str",
                tooltip="Generated first-frame mask path.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="first_frame_path",
                output_type="str",
                tooltip="Extracted first-frame image path, if saved.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="sam2_model_cache_path",
                output_type="str",
                tooltip="Resolved local SAM2 cache directory.",
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

    @staticmethod
    def _clamp_ratio(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _read_first_frame(video_path: Path) -> np.ndarray:
        cap = cv2.VideoCapture(str(video_path))
        try:
            ok, frame_bgr = cap.read()
        finally:
            cap.release()

        if not ok or frame_bgr is None:
            raise ValueError("Unable to read first frame from input video.")
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _save_rgb_png(rgb_frame: np.ndarray, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.fromarray(rgb_frame.astype(np.uint8), mode="RGB")
        image.save(output_path)

    @staticmethod
    def _save_mask_png(mask_u8: np.ndarray, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.fromarray(mask_u8.astype(np.uint8), mode="L")
        image.save(output_path)

    def process(self) -> None:
        video_path_text = self._safe_str(self.parameter_values.get("input_video_path", ""))
        output_mask_text = self._safe_str(self.parameter_values.get("output_mask_path", ""))
        save_first_frame = bool(self.parameter_values.get("save_first_frame", True))
        x_ratio = self._clamp_ratio(float(self.parameter_values.get("positive_point_x_ratio", 0.5)))
        y_ratio = self._clamp_ratio(float(self.parameter_values.get("positive_point_y_ratio", 0.5)))
        mask_threshold = float(self.parameter_values.get("mask_threshold", 0.0))
        multimask_output = bool(self.parameter_values.get("multimask_output", True))

        if not video_path_text:
            self.parameter_output_values["output_mask_path_out"] = ""
            self.parameter_output_values["first_frame_path"] = ""
            self.parameter_output_values["sam2_model_cache_path"] = ""
            self.parameter_output_values["status_message"] = "input_video_path is required."
            return

        video_path = Path(video_path_text)
        if not video_path.exists():
            self.parameter_output_values["output_mask_path_out"] = ""
            self.parameter_output_values["first_frame_path"] = ""
            self.parameter_output_values["sam2_model_cache_path"] = ""
            self.parameter_output_values["status_message"] = f"Input video path not found: {video_path}"
            return

        default_mask_path = video_path.parent / f"{video_path.stem}_mask.png"
        mask_output_path = Path(output_mask_text) if output_mask_text else default_mask_path
        first_frame_output_path = video_path.parent / f"{video_path.stem}_first_frame.png"

        try:
            first_frame = self._read_first_frame(video_path)
            frame_h, frame_w = first_frame.shape[:2]

            if save_first_frame:
                self._save_rgb_png(first_frame, first_frame_output_path)

            sam2_config_name, sam2_checkpoint_name = HF_MODEL_ID_TO_FILENAMES[self.SAM2_REPO_ID]
            sam2_ckpt_path = hf_hub_download(
                repo_id=self.SAM2_REPO_ID,
                filename=sam2_checkpoint_name,
            )
            sam2_cache_path = snapshot_download(repo_id=self.SAM2_REPO_ID)

            sam2_model = build_sam2(
                config_file=sam2_config_name,
                ckpt_path=sam2_ckpt_path,
                device="cpu",
            )
            predictor = SAM2ImagePredictor(
                sam_model=sam2_model,
                mask_threshold=mask_threshold,
            )
            predictor.set_image(first_frame)

            point_coords = np.asarray([[x_ratio * (frame_w - 1), y_ratio * (frame_h - 1)]], dtype=np.float32)
            point_labels = np.asarray([1], dtype=np.int32)
            masks, scores, _logits = predictor.predict(
                point_coords=point_coords,
                point_labels=point_labels,
                multimask_output=multimask_output,
            )

            if masks.ndim == 2:
                best_mask = masks
                best_score = float(scores[0]) if len(scores) else 0.0
            else:
                best_idx = int(np.argmax(scores)) if len(scores) else 0
                best_mask = masks[best_idx]
                best_score = float(scores[best_idx]) if len(scores) else 0.0

            mask_u8 = (best_mask.astype(np.uint8) * 255).astype(np.uint8)
            self._save_mask_png(mask_u8, mask_output_path)

            status = (
                "Created first-frame mask with SAM2 auto point prompt. "
                f"Best score: {best_score:.4f}"
            )
            logger.info(status)
            self.parameter_output_values["output_mask_path_out"] = str(mask_output_path)
            self.parameter_output_values["first_frame_path"] = str(first_frame_output_path) if save_first_frame else ""
            self.parameter_output_values["sam2_model_cache_path"] = self._safe_str(sam2_cache_path)
            self.parameter_output_values["status_message"] = status
        except Exception as exc:
            error_status = f"SAM2 auto mask generation failed: {exc}"
            logger.exception(error_status)
            self.parameter_output_values["output_mask_path_out"] = ""
            self.parameter_output_values["first_frame_path"] = ""
            self.parameter_output_values["sam2_model_cache_path"] = ""
            self.parameter_output_values["status_message"] = error_status
