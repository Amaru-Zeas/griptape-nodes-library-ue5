from __future__ import annotations

import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import PIL.Image
import torch

logger = logging.getLogger(__name__)


class MaskTrackerBackend(ABC):
    @abstractmethod
    def generate_masks(
        self,
        frames: list[PIL.Image.Image],
        prompt: str,
        prompt_frame_idx: int,
        box_threshold: float,
        text_threshold: float,
        device: torch.device,
    ) -> list[PIL.Image.Image]:
        raise NotImplementedError


class Sam2Backend(MaskTrackerBackend):
    def __init__(self, dino_model: str, sam2_model: str):
        self._dino_model = dino_model
        self._sam2_model = sam2_model

    def _to_rgb_mask(self, mask_2d: np.ndarray) -> PIL.Image.Image:
        mask = np.clip(mask_2d, 0, 255).astype(np.uint8)
        return PIL.Image.fromarray(mask, mode="L").convert("RGB")

    def generate_masks(  # noqa: PLR0915
        self,
        frames: list[PIL.Image.Image],
        prompt: str,
        prompt_frame_idx: int,
        box_threshold: float,
        text_threshold: float,
        device: torch.device,
    ) -> list[PIL.Image.Image]:
        from huggingface_hub import hf_hub_download
        from sam2.build_sam import HF_MODEL_ID_TO_FILENAMES, build_sam2_video_predictor
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

        if not frames:
            raise ValueError("No frames found for SAM2 segmentation.")
        if not prompt.strip():
            raise ValueError("Prompt is required for sam2 backend.")

        prompt_frame_idx = max(0, min(prompt_frame_idx, len(frames) - 1))

        dino_processor = AutoProcessor.from_pretrained(self._dino_model, local_files_only=True)
        dino_model = AutoModelForZeroShotObjectDetection.from_pretrained(self._dino_model, local_files_only=True)
        dino_model.to(device)

        sam2_config_name, sam2_checkpoint_name = HF_MODEL_ID_TO_FILENAMES[self._sam2_model]
        sam2_ckpt_path = hf_hub_download(
            repo_id=self._sam2_model,
            filename=sam2_checkpoint_name,
            local_files_only=True,
        )
        predictor = build_sam2_video_predictor(config_file=sam2_config_name, ckpt_path=sam2_ckpt_path, device=device)

        prompt_frame = frames[prompt_frame_idx]
        inputs = dino_processor(images=prompt_frame, text=prompt.lower(), return_tensors="pt")
        inputs.to(device=dino_model.device)
        with torch.no_grad():
            outputs = dino_model(**inputs)
        dino_results = dino_processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=box_threshold,
            text_threshold=text_threshold,
            target_sizes=[prompt_frame.size[::-1]],
        )
        boxes = dino_results[0]["boxes"].cpu().numpy() if dino_results and len(dino_results[0]["boxes"]) > 0 else []
        if len(boxes) == 0:
            logger.info("SAM2 backend: no DINO boxes found; returning empty masks.")
            black = PIL.Image.new("RGB", frames[0].size, (0, 0, 0))
            return [black.copy() for _ in range(len(frames))]

        with tempfile.TemporaryDirectory() as tmp_dir:
            frame_dir = Path(tmp_dir) / "frames"
            frame_dir.mkdir(parents=True, exist_ok=True)
            for i, frame in enumerate(frames):
                frame.save(frame_dir / f"{i:05d}.jpg", format="JPEG")

            inference_state = predictor.init_state(video_path=str(frame_dir))
            for obj_id, box in enumerate(boxes, start=1):
                predictor.add_new_points_or_box(
                    inference_state=inference_state,
                    frame_idx=prompt_frame_idx,
                    obj_id=obj_id,
                    box=box,
                )

            video_segments: dict[int, dict[int, np.ndarray]] = {}
            for out_frame_idx, out_obj_ids, out_mask_logits in predictor.propagate_in_video(inference_state):
                video_segments[out_frame_idx] = {
                    out_obj_id: (out_mask_logits[i] > 0.0).cpu().numpy()
                    for i, out_obj_id in enumerate(out_obj_ids)
                }

        masks: list[PIL.Image.Image] = []
        for frame_idx, frame in enumerate(frames):
            combined_mask = np.zeros(frame.size[::-1], dtype=np.uint8)
            for mask_tensor in video_segments.get(frame_idx, {}).values():
                if mask_tensor is None:
                    continue
                mask = (mask_tensor * 255).astype(np.uint8).squeeze()
                combined_mask = np.maximum(combined_mask, mask)
            masks.append(self._to_rgb_mask(combined_mask))
        return masks


class Sam3Backend(MaskTrackerBackend):
    def generate_masks(
        self,
        frames: list[PIL.Image.Image],
        prompt: str,
        prompt_frame_idx: int,
        box_threshold: float,
        text_threshold: float,
        device: torch.device,
    ) -> list[PIL.Image.Image]:
        del frames, prompt, prompt_frame_idx, box_threshold, text_threshold, device
        raise NotImplementedError(
            "SAM3 backend scaffold is present but not implemented yet. Use `none` or `sam2` for now."
        )


def create_backend(backend_name: str, dino_model: str, sam2_model: str) -> MaskTrackerBackend:
    key = backend_name.strip().lower()
    if key == "sam2":
        return Sam2Backend(dino_model=dino_model, sam2_model=sam2_model)
    if key == "sam3":
        return Sam3Backend()
    raise ValueError(f"Unsupported backend '{backend_name}'.")
