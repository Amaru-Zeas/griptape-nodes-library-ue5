import base64
import io
import logging
from typing import Any
from urllib.error import URLError

import numpy as np
import PIL.Image  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.loaders import ImageLoader
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.files.file import File
from griptape_nodes.traits.widget import Widget
from huggingface_hub import hf_hub_download  # pyright: ignore[reportMissingImports]
from requests.exceptions import RequestException
from sam2.build_sam import HF_MODEL_ID_TO_FILENAMES, build_sam2  # type: ignore[reportMissingImports]
from sam2.sam2_image_predictor import SAM2ImagePredictor  # type: ignore[reportMissingImports]

logger = logging.getLogger("sam2_point_picker_library")


class Sam2PointSegmenterNode(ControlNode):
    """Interactive SAM2 point-based image segmentation node."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._huggingface_sam2_repo_parameter = HuggingFaceRepoParameter(
            self,
            repo_ids=[
                "facebook/sam2-hiera-tiny",
                "facebook/sam2-hiera-small",
                "facebook/sam2-hiera-base-plus",
                "facebook/sam2-hiera-large",
            ],
            parameter_name="sam2_model",
        )
        self._huggingface_sam2_repo_parameter.add_input_parameters()

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image for point-driven segmentation.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="mask_threshold",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Threshold used when converting SAM logits to binary masks.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="multimask_output",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Return multiple mask candidates and keep the highest score.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="sam2_point_widget",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={
                    "imageDataUrl": "",
                    "imageWidth": 0,
                    "imageHeight": 0,
                    "points": [],
                    "activeLabel": 1,
                    "statusMessage": "Load image, click points, then run node.",
                },
                tooltip="Interactive SAM2 point picker widget.",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="Sam2PointPickerWidget", library="SAM2 Point Picker Library")},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_mask",
                output_type="ImageArtifact",
                tooltip="Point-guided SAM2 segmentation mask.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="sam_points",
                output_type="dict",
                tooltip="Point payload for downstream reuse.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status_message",
                output_type="str",
                tooltip="Segmentation status.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    @staticmethod
    def _to_data_url(image_pil: PIL.Image.Image) -> str:
        # Keep widget payload small; full-res base64 previews can exceed UI state limits.
        max_preview_side = 1280
        preview = image_pil.convert("RGB")
        width, height = preview.size
        largest_side = max(width, height)
        if largest_side > max_preview_side and largest_side > 0:
            scale = max_preview_side / float(largest_side)
            preview = preview.resize(
                (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                PIL.Image.Resampling.LANCZOS,
            )

        buffer = io.BytesIO()
        preview.save(buffer, format="JPEG", quality=72, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"

    @staticmethod
    def _artifact_to_pil(image_artifact: ImageArtifact) -> PIL.Image.Image:
        if not isinstance(image_artifact.value, (bytes, bytearray)):
            raise ValueError("input_image artifact does not contain binary image bytes.")
        image_pil = PIL.Image.open(io.BytesIO(image_artifact.value))
        if image_pil.mode == "RGBA":
            black_background = PIL.Image.new("RGBA", image_pil.size, (0, 0, 0, 255))
            image_pil = PIL.Image.alpha_composite(black_background, image_pil)
        return image_pil.convert("RGB")

    @staticmethod
    def _pil_to_artifact(image_pil: PIL.Image.Image) -> ImageArtifact:
        output = io.BytesIO()
        image_pil.save(output, format="PNG")
        return ImageArtifact(
            value=output.getvalue(),
            width=image_pil.width,
            height=image_pil.height,
            format="png",
        )

    @staticmethod
    def _load_image_from_url_artifact(image_url_artifact: ImageUrlArtifact) -> ImageArtifact:
        try:
            image_bytes = File(image_url_artifact.value).read_bytes()
        except (URLError, RequestException, ConnectionError, TimeoutError, OSError) as err:
            details = (
                f"Failed to download image at '{image_url_artifact.value}'. "
                f"Error: {err}"
            )
            raise ValueError(details) from err
        return ImageLoader().parse(image_bytes)

    def _get_input_image_pil(self) -> PIL.Image.Image:
        input_image_artifact = self.get_parameter_value("input_image")
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = self._load_image_from_url_artifact(input_image_artifact)
        if not isinstance(input_image_artifact, ImageArtifact):
            raise ValueError("input_image must be ImageArtifact or ImageUrlArtifact.")
        return self._artifact_to_pil(input_image_artifact)

    @staticmethod
    def _parse_points(widget_state: dict[str, Any], width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
        points = widget_state.get("points", [])
        if not isinstance(points, list):
            return np.zeros((0, 2), dtype=np.float32), np.zeros((0,), dtype=np.int32)

        coords: list[list[float]] = []
        labels: list[int] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            try:
                x = float(point.get("x", 0.0))
                y = float(point.get("y", 0.0))
                label = int(point.get("label", 1))
            except (TypeError, ValueError):
                continue

            x = max(0.0, min(float(width - 1), x))
            y = max(0.0, min(float(height - 1), y))
            label = 1 if label > 0 else 0
            coords.append([x, y])
            labels.append(label)

        if not coords:
            return np.zeros((0, 2), dtype=np.float32), np.zeros((0,), dtype=np.int32)
        return np.asarray(coords, dtype=np.float32), np.asarray(labels, dtype=np.int32)

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        image_pil = self._get_input_image_pil()
        image_np = np.array(image_pil)
        image_h, image_w = image_np.shape[:2]
        image_data_url = self._to_data_url(image_pil)

        widget_state = self.get_parameter_value("sam2_point_widget") or {}
        if not isinstance(widget_state, dict):
            widget_state = {}

        point_coords, point_labels = self._parse_points(widget_state, image_w, image_h)
        points_payload = {
            "points": point_coords.tolist(),
            "labels": point_labels.tolist(),
            "image_width": image_w,
            "image_height": image_h,
        }

        if point_coords.shape[0] == 0:
            empty_mask = np.zeros((image_h, image_w), dtype=np.uint8)
            output_mask_artifact = self._pil_to_artifact(PIL.Image.fromarray(empty_mask, mode="L"))
            status_message = "No points selected. Add positive/negative points in widget and run again."

            self.parameter_output_values["output_mask"] = output_mask_artifact
            self.parameter_output_values["sam_points"] = points_payload
            self.parameter_output_values["status_message"] = status_message
            self.parameter_output_values["sam2_point_widget"] = {
                "imageDataUrl": image_data_url,
                "imageWidth": image_w,
                "imageHeight": image_h,
                "points": widget_state.get("points", []),
                "activeLabel": int(widget_state.get("activeLabel", 1) or 1),
                "statusMessage": status_message,
            }
            return

        sam2_repo_id, sam2_revision = self._huggingface_sam2_repo_parameter.get_repo_revision()
        sam2_config_name, sam2_checkpoint_name = HF_MODEL_ID_TO_FILENAMES[sam2_repo_id]
        sam2_ckpt_path = hf_hub_download(
            repo_id=sam2_repo_id,
            filename=sam2_checkpoint_name,
            revision=sam2_revision,
            local_files_only=True,
        )

        sam2_model = build_sam2(config_file=sam2_config_name, ckpt_path=sam2_ckpt_path, device="cpu")
        predictor = SAM2ImagePredictor(
            sam_model=sam2_model,
            mask_threshold=float(self.get_parameter_value("mask_threshold")),
        )

        device = "cuda" if torch.cuda.is_available() else "cpu"
        sam2_model.to(device)

        predictor.set_image(image_np)
        masks, scores, _logits = predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=bool(self.get_parameter_value("multimask_output")),
        )

        if masks.ndim == 2:
            best_mask = masks
            best_score = float(scores[0]) if len(scores) else 0.0
        else:
            best_index = int(np.argmax(scores)) if len(scores) else 0
            best_mask = masks[best_index]
            best_score = float(scores[best_index]) if len(scores) else 0.0

        output_mask = (best_mask.astype(np.uint8) * 255).astype(np.uint8)
        output_mask_artifact = self._pil_to_artifact(PIL.Image.fromarray(output_mask, mode="L"))

        status_message = f"SAM2 mask created from {point_coords.shape[0]} point(s). Best score: {best_score:.4f}"
        logger.info(status_message)

        self.parameter_output_values["output_mask"] = output_mask_artifact
        self.parameter_output_values["sam_points"] = points_payload
        self.parameter_output_values["status_message"] = status_message
        self.parameter_output_values["sam2_point_widget"] = {
            "imageDataUrl": image_data_url,
            "imageWidth": image_w,
            "imageHeight": image_h,
            "points": widget_state.get("points", []),
            "activeLabel": int(widget_state.get("activeLabel", 1) or 1),
            "statusMessage": status_message,
        }
