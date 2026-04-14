from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

import cv2
import imageio.v2 as imageio
import numpy as np
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class AffectedMaskBuilderNode(DataNode):
    """Build affected-region mask video from a primary binary mask video."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "VideoTools",
            "description": "Expand a primary mask into an affected mask for richer VOID quadmask conditioning.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        self.set_initial_node_size(width=520, height=650)

        self.add_parameter(
            Parameter(
                name="input_mask_video",
                input_types=["VideoArtifact", "VideoUrlArtifact", "dict"],
                type="VideoUrlArtifact",
                output_type="VideoUrlArtifact",
                tooltip="Primary binary mask video (white=remove, black=keep).",
            )
        )
        self.add_parameter(
            Parameter(
                name="threshold",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=20,
                tooltip="Binarization threshold for incoming mask frames.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="spatial_dilation_radius",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=12,
                tooltip="Spatial dilation radius (pixels) per frame.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="temporal_dilation_radius",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=2,
                tooltip="Temporal dilation radius (frames) across time.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="exclude_primary_region",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=True,
                tooltip="If true, output only affected region outside the primary mask.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_affected_mask_video",
                output_type="VideoUrlArtifact",
                tooltip="Generated affected-region mask video.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        input_mask_value = self._artifact_value(self.parameter_values.get("input_mask_video"))
        threshold = int(self.parameter_values.get("threshold") or 20)
        spatial_radius = max(0, int(self.parameter_values.get("spatial_dilation_radius") or 12))
        temporal_radius = max(0, int(self.parameter_values.get("temporal_dilation_radius") or 2))
        exclude_primary = bool(self.parameter_values.get("exclude_primary_region") if "exclude_primary_region" in self.parameter_values else True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_dir = Path(tmp_dir)
            input_path = temp_dir / "primary_mask.mp4"
            output_path = temp_dir / f"affected_mask_{uuid.uuid4()}.mp4"
            input_path.write_bytes(File(input_mask_value).read_bytes())

            reader = imageio.get_reader(str(input_path))
            try:
                meta = reader.get_meta_data()
                fps = float(meta.get("fps", 24.0) or 24.0)
                raw_frames = [np.asarray(frame) for frame in reader]
            finally:
                reader.close()

            if not raw_frames:
                raise ValueError("Input mask video has no readable frames.")

            primary_masks: list[np.ndarray] = []
            for frame in raw_frames:
                gray = frame if frame.ndim == 2 else frame[:, :, 0]
                primary_masks.append(gray > threshold)

            if spatial_radius > 0:
                kernel_size = (2 * spatial_radius) + 1
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
                spatial_masks = [
                    cv2.dilate(mask.astype(np.uint8), kernel, iterations=1).astype(bool) for mask in primary_masks
                ]
            else:
                spatial_masks = [mask.copy() for mask in primary_masks]

            if temporal_radius > 0:
                affected_masks: list[np.ndarray] = []
                frame_count = len(spatial_masks)
                for idx in range(frame_count):
                    start = max(0, idx - temporal_radius)
                    end = min(frame_count, idx + temporal_radius + 1)
                    accum = np.zeros_like(spatial_masks[idx], dtype=bool)
                    for j in range(start, end):
                        accum |= spatial_masks[j]
                    affected_masks.append(accum)
            else:
                affected_masks = [mask.copy() for mask in spatial_masks]

            if exclude_primary:
                affected_masks = [np.logical_and(a, np.logical_not(p)) for a, p in zip(affected_masks, primary_masks)]

            out_frames: list[np.ndarray] = []
            for mask in affected_masks:
                mask_u8 = np.where(mask, 255, 0).astype(np.uint8)
                out_frames.append(np.stack([mask_u8, mask_u8, mask_u8], axis=-1))

            imageio.mimsave(str(output_path), out_frames, fps=max(1.0, fps))
            self.parameter_output_values["output_affected_mask_video"] = self._publish_video(output_path)

    def _artifact_value(self, artifact: Any) -> str:
        if artifact is None:
            raise ValueError("input_mask_video is required.")
        if isinstance(artifact, str):
            return artifact
        if isinstance(artifact, dict):
            value = artifact.get("value")
            if isinstance(value, str) and value:
                return value
            raise ValueError("Mask video artifact dict is missing 'value'.")
        value = getattr(artifact, "value", None)
        if isinstance(value, str) and value:
            return value
        raise ValueError("Unsupported mask video input type.")

    def _publish_video(self, video_path: Path) -> VideoUrlArtifact:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        return VideoUrlArtifact(url)

