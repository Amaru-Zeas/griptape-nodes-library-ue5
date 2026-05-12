from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import cv2  # type: ignore[reportMissingImports]
import numpy as np
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.files.file import File


class CorridorKeyInferenceNode(DataNode):
    """Run CorridorKey inference on one clip folder with auto checkpoint download."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "Keying",
            "description": "Run CorridorKey keying with auto model download and simple clip-folder input.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="clip_root_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional: clip folder containing Input + AlphaHint assets.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="input_path",
                input_types=["str", "dict", "FileArtifact", "FileUrlArtifact", "VideoArtifact", "VideoUrlArtifact"],
                type="str",
                default_value="",
                tooltip="Direct input video path, URL, artifact ref, or input sequence folder.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="alpha_hint_path",
                input_types=["str", "dict", "FileArtifact", "FileUrlArtifact", "VideoArtifact", "VideoUrlArtifact"],
                type="str",
                default_value="",
                tooltip="Direct alpha-hint path, URL, artifact ref, or alpha sequence folder.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_parent_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional parent folder for generated run output in direct input mode. Defaults to Griptape output workspace folder.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="backend",
                input_types=["str"],
                type="str",
                default_value="auto",
                tooltip="Backend selection: auto, torch, or mlx.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="device",
                input_types=["str"],
                type="str",
                default_value="auto",
                tooltip="Device selection: auto, cuda, mps, or cpu.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="screen_color",
                input_types=["str"],
                type="str",
                default_value="auto",
                tooltip="Screen color: auto, green, or blue.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="input_is_linear",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Treat input footage as linear colorspace.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="despill_strength",
                input_types=["float"],
                type="float",
                default_value=0.5,
                tooltip="Despill strength (0.0 to 1.0).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="auto_despeckle",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Automatically remove tiny disconnected matte speckles.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="despeckle_size",
                input_types=["int"],
                type="int",
                default_value=400,
                tooltip="Minimum pixel area threshold for despeckle cleanup.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="refiner_scale",
                input_types=["float"],
                type="float",
                default_value=1.0,
                tooltip="Refiner strength multiplier.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="image_size",
                input_types=["int"],
                type="int",
                default_value=2048,
                tooltip="Inference image size (typically 2048).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="tiled_inference",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Enable tiled inference for MLX backend.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="max_frames",
                input_types=["int"],
                type="int",
                default_value=-1,
                tooltip="Optional frame cap. Use -1 to process all frames.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="skip_existing",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Skip frames that already have output renders.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="auto_alpha_hint_if_missing",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Generate a coarse alpha hint automatically if alpha_hint_path is not connected.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_root_path",
                output_type="str",
                tooltip="Clip Output root path.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="fg_output_dir",
                output_type="str",
                tooltip="Foreground output directory.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="matte_output_dir",
                output_type="str",
                tooltip="Matte output directory.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="comp_output_dir",
                output_type="str",
                tooltip="Comp preview output directory.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="processed_output_dir",
                output_type="str",
                tooltip="Processed RGBA output directory.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status_message",
                output_type="str",
                tooltip="Execution status message.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    @staticmethod
    def _safe_str(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _extract_reference_text(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, Path):
            return str(value).strip()
        if isinstance(value, dict):
            for key in ("path", "value", "url", "uri", "file_path", "local_path"):
                raw = value.get(key)
                if raw:
                    return str(raw).strip()
            return ""
        for attr in ("path", "value", "url", "uri", "file_path", "local_path"):
            raw = getattr(value, attr, None)
            if raw:
                return str(raw).strip()
        return str(value or "").strip()

    @staticmethod
    def _is_url(text: str) -> bool:
        parsed = urlparse(text)
        return parsed.scheme in {"http", "https", "file"}

    @staticmethod
    def _url_suffix(url: str, fallback: str = ".bin") -> str:
        suffix = Path(urlparse(url).path).suffix
        return suffix if suffix else fallback

    @staticmethod
    def _griptape_nodes_base_dir() -> Path:
        env_home = os.environ.get("GRIPTAPE_NODES_HOME", "").strip()
        if env_home:
            return Path(env_home)
        return Path.home() / "GriptapeNodes"

    def _expand_griptape_token_paths(self, reference: str) -> list[Path]:
        text = reference.strip().replace("\\", "/")
        base = self._griptape_nodes_base_dir()
        token_map = {
            "{inputs}": [base / "inputs", base / "Input"],
            "{input}": [base / "inputs", base / "Input"],
            "{outputs}": [base / "outputs", base / "Output"],
            "{output}": [base / "outputs", base / "Output"],
        }

        lowered = text.lower()
        for token, roots in token_map.items():
            idx = lowered.find(token)
            if idx >= 0:
                suffix = text[idx + len(token) :].lstrip("/\\")
                return [root / suffix for root in roots]
        return []

    @staticmethod
    def _default_output_parent_dir() -> Path:
        base = CorridorKeyInferenceNode._griptape_nodes_base_dir()
        preferred = [base / "outputs", base / "Output"]
        for candidate in preferred:
            if candidate.exists():
                return candidate
        return preferred[0]

    def _download_url_to_cache(self, url: str, label: str) -> Path:
        cache_dir = Path(tempfile.gettempdir()) / "corridorkey_node_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        suffix = self._url_suffix(url, fallback=".mp4" if label == "input" else ".png")
        cached_file = cache_dir / f"{label}_{digest}{suffix}"
        if not cached_file.exists():
            data = File(url).read_bytes()
            cached_file.write_bytes(data)
        return cached_file

    def _resolve_to_local_path(self, raw_value: Any, label: str) -> Path:
        reference = self._extract_reference_text(raw_value)
        if not reference:
            raise ValueError(f"{label} is required.")

        token_candidates = self._expand_griptape_token_paths(reference)
        for candidate in token_candidates:
            if candidate.exists():
                return candidate

        expanded = os.path.expandvars(os.path.expanduser(reference))
        local_candidate = Path(expanded)
        if local_candidate.exists():
            return local_candidate

        if self._is_url(reference):
            return self._download_url_to_cache(reference, label=label)

        raise ValueError(f"{label} could not be resolved to a local path or URL: {reference}")

    @staticmethod
    def _is_video_file(path: Path) -> bool:
        return path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}

    @staticmethod
    def _is_image_file(path: Path) -> bool:
        return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp"}

    def _set_failure(self, message: str) -> None:
        self.parameter_output_values["output_root_path"] = ""
        self.parameter_output_values["fg_output_dir"] = ""
        self.parameter_output_values["matte_output_dir"] = ""
        self.parameter_output_values["comp_output_dir"] = ""
        self.parameter_output_values["processed_output_dir"] = ""
        self.parameter_output_values["status_message"] = message

    @staticmethod
    def _exr_write_supported() -> bool:
        probe = np.zeros((2, 2, 3), dtype=np.float32)
        probe_path = Path(tempfile.gettempdir()) / "corridorkey_exr_probe.exr"
        try:
            ok = bool(cv2.imwrite(str(probe_path), probe))
            return ok
        except Exception:
            return False
        finally:
            try:
                if probe_path.exists():
                    probe_path.unlink()
            except Exception:
                pass

    def _resolve_asset_type(self, path: Path) -> str:
        if path.is_dir():
            has_images = any(self._is_image_file(p) for p in path.iterdir() if p.is_file())
            if not has_images:
                raise ValueError(f"Sequence folder has no image files: {path}")
            return "sequence"
        if path.is_file() and self._is_video_file(path):
            return "video"
        raise ValueError(f"Unsupported asset path (need video file or image-sequence folder): {path}")

    @staticmethod
    def _sorted_sequence_files(folder: Path) -> list[Path]:
        return sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp"
        }])

    def _read_image_frame(self, path: Path, assume_linear_exr: bool) -> np.ndarray:
        if path.suffix.lower() == ".exr":
            img = cv2.imread(str(path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_UNCHANGED)
            if img is None:
                raise ValueError(f"Could not read image: {path}")
            if img.ndim == 2:
                img = np.stack([img, img, img], axis=2)
            if img.shape[2] > 3:
                img = img[:, :, :3]
            if img.dtype == np.uint8:
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            elif img.dtype == np.uint16:
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 65535.0
            else:
                rgb = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_BGR2RGB)
            if assume_linear_exr:
                return np.clip(rgb, 0.0, 1.0).astype(np.float32)
            return np.clip(rgb, 0.0, 1.0).astype(np.float32)

        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"Could not read image: {path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return np.clip(rgb, 0.0, 1.0).astype(np.float32)

    def _read_mask_frame(self, path: Path) -> np.ndarray:
        mask = cv2.imread(str(path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_UNCHANGED)
        if mask is None:
            raise ValueError(f"Could not read alpha hint: {path}")
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        if mask.dtype == np.uint8:
            mask = mask.astype(np.float32) / 255.0
        elif mask.dtype == np.uint16:
            mask = mask.astype(np.float32) / 65535.0
        else:
            mask = mask.astype(np.float32)
        return np.clip(mask, 0.0, 1.0)

    @staticmethod
    def _auto_alpha_from_green(rgb: np.ndarray) -> np.ndarray:
        # Fast coarse hint: foreground where non-green dominates.
        r = rgb[:, :, 0]
        g = rgb[:, :, 1]
        b = rgb[:, :, 2]
        green_excess = g - np.maximum(r, b)
        alpha = 1.0 - np.clip((green_excess - 0.02) / 0.45, 0.0, 1.0)
        alpha = np.clip(alpha, 0.0, 1.0).astype(np.float32)
        alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.1, sigmaY=1.1)
        return np.clip(alpha, 0.0, 1.0)

    def _find_clip_assets(self, clip_root: Path) -> tuple[Path, Path | None]:
        input_dir = clip_root / "Input"
        alpha_dir = clip_root / "AlphaHint"

        input_path: Path | None = None
        alpha_path: Path | None = None

        if input_dir.is_dir():
            input_path = input_dir
        else:
            candidates = [p for p in clip_root.iterdir() if p.is_file() and p.stem.lower() == "input" and self._is_video_file(p)]
            if candidates:
                input_path = candidates[0]

        if alpha_dir.is_dir():
            alpha_path = alpha_dir
        else:
            candidates = [p for p in clip_root.iterdir() if p.is_file() and p.stem.lower() == "alphahint" and self._is_video_file(p)]
            if candidates:
                alpha_path = candidates[0]

        if input_path is None:
            raise ValueError(f"No Input asset found in clip root: {clip_root}")
        return input_path, alpha_path

    @staticmethod
    def _prepare_corridorkey_backend_paths() -> None:
        """Normalize CorridorKey backend checkpoint paths to absolute directories."""
        import CorridorKeyModule.backend as ck_backend  # type: ignore[reportMissingImports]

        checkpoints_dir = Path(ck_backend.__file__).resolve().parent / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)
        ck_backend.CHECKPOINT_DIR = str(checkpoints_dir)

    @staticmethod
    def _resolve_runtime_device(device_value: str) -> str:
        requested = (device_value or "auto").strip().lower()
        if requested in {"cpu", "cuda", "mps"}:
            return requested
        if requested != "auto":
            return "cpu"
        try:
            import torch  # type: ignore[reportMissingImports]

            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        except Exception:
            return "cpu"

    def _resolve_screen_color_auto(
        self,
        requested_color: str,
        input_path: Path,
        input_type: str,
        alpha_path: Path | None,
        alpha_type: str | None,
        input_is_linear: bool,
    ) -> str:
        requested = (requested_color or "auto").strip().lower()
        if requested in {"green", "blue"}:
            return requested

        # Default fallback if we cannot sample.
        fallback = "green"
        try:
            from CorridorKeyModule.core.color_utils import estimate_screen_color
        except Exception:
            return fallback

        try:
            if input_type == "video":
                cap = cv2.VideoCapture(str(input_path))
                ok, frame_bgr = cap.read()
                cap.release()
                if not ok or frame_bgr is None:
                    return fallback
                sample_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            else:
                seq = self._sorted_sequence_files(input_path)
                if not seq:
                    return fallback
                sample_rgb = self._read_image_frame(seq[0], assume_linear_exr=input_is_linear)

            if alpha_path is not None and alpha_type is not None:
                if alpha_type == "video":
                    cap = cv2.VideoCapture(str(alpha_path))
                    ok, frame = cap.read()
                    cap.release()
                    if ok and frame is not None:
                        sample_alpha = frame[:, :, 2].astype(np.float32) / 255.0
                    else:
                        sample_alpha = self._auto_alpha_from_green(sample_rgb)
                else:
                    seq = self._sorted_sequence_files(alpha_path)
                    sample_alpha = self._read_mask_frame(seq[0]) if seq else self._auto_alpha_from_green(sample_rgb)
            else:
                sample_alpha = self._auto_alpha_from_green(sample_rgb)

            if sample_alpha.shape[:2] != sample_rgb.shape[:2]:
                sample_alpha = cv2.resize(
                    sample_alpha,
                    (sample_rgb.shape[1], sample_rgb.shape[0]),
                    interpolation=cv2.INTER_LINEAR,
                )
            detected = str(estimate_screen_color(sample_rgb, sample_alpha)).strip().lower()
            return detected if detected in {"green", "blue"} else fallback
        except Exception:
            return fallback

    def process(self) -> None:
        clip_root_text = self._safe_str(self.parameter_values.get("clip_root_path", ""))
        input_raw = self.parameter_values.get("input_path", "")
        alpha_raw = self.parameter_values.get("alpha_hint_path", "")
        output_parent_text = self._safe_str(self.parameter_values.get("output_parent_path", ""))
        backend = self._safe_str(self.parameter_values.get("backend", "auto")) or "auto"
        device = self._safe_str(self.parameter_values.get("device", "auto")) or "auto"
        screen_color = self._safe_str(self.parameter_values.get("screen_color", "auto")) or "auto"
        input_is_linear = bool(self.parameter_values.get("input_is_linear", False))
        despill_strength = float(self.parameter_values.get("despill_strength", 0.5))
        auto_despeckle = bool(self.parameter_values.get("auto_despeckle", True))
        despeckle_size = int(self.parameter_values.get("despeckle_size", 400))
        refiner_scale = float(self.parameter_values.get("refiner_scale", 1.0))
        image_size = int(self.parameter_values.get("image_size", 2048))
        tiled_inference = bool(self.parameter_values.get("tiled_inference", False))
        max_frames = int(self.parameter_values.get("max_frames", -1))
        skip_existing = bool(self.parameter_values.get("skip_existing", True))
        auto_alpha_hint = bool(self.parameter_values.get("auto_alpha_hint_if_missing", True))
        resolved_device = self._resolve_runtime_device(device)

        try:
            self._prepare_corridorkey_backend_paths()
            from CorridorKeyModule.backend import DEFAULT_MLX_TILE_SIZE, create_engine
        except Exception as exc:
            self._set_failure(
                f"Could not import CorridorKey engine modules. Ensure dependency is installed correctly: {exc}"
            )
            return

        try:
            if clip_root_text:
                clip_root = Path(clip_root_text)
                if not clip_root.exists() or not clip_root.is_dir():
                    raise ValueError(f"Clip folder not found: {clip_root}")
                input_path, alpha_path = self._find_clip_assets(clip_root)
                run_root = clip_root
            else:
                input_path = self._resolve_to_local_path(input_raw, "input_path")
                alpha_ref = self._extract_reference_text(alpha_raw)
                alpha_path = self._resolve_to_local_path(alpha_raw, "alpha_hint_path") if alpha_ref else None
                output_parent = Path(output_parent_text) if output_parent_text else self._default_output_parent_dir()
                run_root = output_parent / f"{input_path.stem}_corridorkey_run"
                run_root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._set_failure(f"Input resolution failed: {exc}")
            return

        try:
            input_type = self._resolve_asset_type(input_path)
            alpha_type = self._resolve_asset_type(alpha_path) if alpha_path is not None else None
        except Exception as exc:
            self._set_failure(f"Asset parsing failed: {exc}")
            return

        resolved_screen_color = self._resolve_screen_color_auto(
            requested_color=screen_color,
            input_path=input_path,
            input_type=input_type,
            alpha_path=alpha_path,
            alpha_type=alpha_type,
            input_is_linear=input_is_linear,
        )

        output_root = run_root / "Output"
        fg_dir = output_root / "FG"
        matte_dir = output_root / "Matte"
        comp_dir = output_root / "Comp"
        processed_dir = output_root / "Processed"
        for folder in (fg_dir, matte_dir, comp_dir, processed_dir):
            folder.mkdir(parents=True, exist_ok=True)

        try:
            engine = create_engine(
                backend=backend,
                device=resolved_device,
                tile_size=DEFAULT_MLX_TILE_SIZE if tiled_inference else None,
                img_size=image_size,
                screen_color=resolved_screen_color,
            )
        except Exception as exc:
            self._set_failure(f"Failed to create CorridorKey engine: {exc}")
            return

        can_write_exr = self._exr_write_supported()
        fg_ext = ".exr" if can_write_exr else ".png"
        matte_ext = ".exr" if can_write_exr else ".png"
        processed_ext = ".exr" if can_write_exr else ".png"

        try:
            if input_type == "video":
                input_cap = cv2.VideoCapture(str(input_path))
                if not input_cap.isOpened():
                    raise ValueError(f"Could not open input video: {input_path}")
                input_total = int(input_cap.get(cv2.CAP_PROP_FRAME_COUNT))
                input_seq_files: list[Path] = []
            else:
                input_cap = None
                input_seq_files = self._sorted_sequence_files(input_path)
                input_total = len(input_seq_files)
                if input_total == 0:
                    raise ValueError(f"No frames found in input sequence: {input_path}")

            if alpha_path is not None:
                if alpha_type == "video":
                    alpha_cap = cv2.VideoCapture(str(alpha_path))
                    if not alpha_cap.isOpened():
                        raise ValueError(f"Could not open alpha video: {alpha_path}")
                    alpha_total = int(alpha_cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    alpha_seq_files: list[Path] = []
                else:
                    alpha_cap = None
                    alpha_seq_files = self._sorted_sequence_files(alpha_path)
                    alpha_total = len(alpha_seq_files)
                    if alpha_total == 0:
                        raise ValueError(f"No frames found in alpha sequence: {alpha_path}")
            else:
                alpha_cap = None
                alpha_seq_files = []
                alpha_total = input_total

            if alpha_path is not None and input_total != alpha_total:
                raise ValueError(f"Frame count mismatch. Input: {input_total}, Alpha: {alpha_total}")

            process_total = input_total if max_frames <= 0 else min(input_total, max_frames)
            if process_total <= 0:
                raise ValueError("No frames to process.")

            used_auto_alpha = alpha_path is None
            if used_auto_alpha and not auto_alpha_hint:
                raise ValueError("alpha_hint_path is missing and auto_alpha_hint_if_missing is disabled.")

            for i in range(process_total):
                stem = f"{i:05d}" if input_type == "video" else input_seq_files[i].stem
                if skip_existing and (comp_dir / f"{stem}.png").exists():
                    if input_cap is not None:
                        input_cap.read()
                    if alpha_cap is not None:
                        alpha_cap.read()
                    continue

                if input_cap is not None:
                    ok, frame_bgr = input_cap.read()
                    if not ok or frame_bgr is None:
                        raise ValueError(f"Failed reading input frame {i}.")
                    img_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
                else:
                    img_rgb = self._read_image_frame(input_seq_files[i], assume_linear_exr=input_is_linear)

                if alpha_path is None:
                    mask_linear = self._auto_alpha_from_green(img_rgb)
                elif alpha_cap is not None:
                    ok, frame = alpha_cap.read()
                    if not ok or frame is None:
                        raise ValueError(f"Failed reading alpha frame {i}.")
                    mask_linear = frame[:, :, 2].astype(np.float32) / 255.0
                else:
                    mask_linear = self._read_mask_frame(alpha_seq_files[i])

                if mask_linear.shape[:2] != img_rgb.shape[:2]:
                    mask_linear = cv2.resize(mask_linear, (img_rgb.shape[1], img_rgb.shape[0]), interpolation=cv2.INTER_LINEAR)

                result = engine.process_frame(
                    img_rgb,
                    mask_linear,
                    input_is_linear=input_is_linear,
                    fg_is_straight=True,
                    despill_strength=max(0.0, min(1.0, despill_strength)),
                    auto_despeckle=auto_despeckle,
                    despeckle_size=max(0, despeckle_size),
                    refiner_scale=refiner_scale,
                    generate_comp=True,
                    post_process_on_gpu=False,
                )

                fg = result["fg"]
                alpha = result["alpha"]
                comp = result.get("comp")
                processed = result.get("processed")

                fg_bgr_f32 = cv2.cvtColor(np.clip(fg, 0.0, 1.0).astype(np.float32), cv2.COLOR_RGB2BGR)
                if can_write_exr:
                    cv2.imwrite(str(fg_dir / f"{stem}{fg_ext}"), fg_bgr_f32)
                else:
                    cv2.imwrite(str(fg_dir / f"{stem}{fg_ext}"), (fg_bgr_f32 * 255.0).astype(np.uint8))

                if alpha.ndim == 3:
                    alpha = alpha[:, :, 0]
                alpha = np.clip(alpha, 0.0, 1.0).astype(np.float32)
                if can_write_exr:
                    cv2.imwrite(str(matte_dir / f"{stem}{matte_ext}"), alpha)
                else:
                    cv2.imwrite(str(matte_dir / f"{stem}{matte_ext}"), (alpha * 255.0).astype(np.uint8))

                if comp is not None:
                    comp_u8 = (np.clip(comp, 0.0, 1.0) * 255.0).astype(np.uint8)
                    comp_bgr = cv2.cvtColor(comp_u8, cv2.COLOR_RGB2BGR)
                    cv2.imwrite(str(comp_dir / f"{stem}.png"), comp_bgr)

                if processed is not None:
                    if processed.ndim == 3 and processed.shape[2] == 4:
                        proc_bgra_f32 = cv2.cvtColor(
                            np.clip(processed, 0.0, 1.0).astype(np.float32),
                            cv2.COLOR_RGBA2BGRA,
                        )
                        if can_write_exr:
                            cv2.imwrite(str(processed_dir / f"{stem}{processed_ext}"), proc_bgra_f32)
                        else:
                            cv2.imwrite(
                                str(processed_dir / f"{stem}{processed_ext}"),
                                (proc_bgra_f32 * 255.0).astype(np.uint8),
                            )

            if input_cap is not None:
                input_cap.release()
            if alpha_cap is not None:
                alpha_cap.release()

            self.parameter_output_values["output_root_path"] = str(output_root)
            self.parameter_output_values["fg_output_dir"] = str(fg_dir)
            self.parameter_output_values["matte_output_dir"] = str(matte_dir)
            self.parameter_output_values["comp_output_dir"] = str(comp_dir)
            self.parameter_output_values["processed_output_dir"] = str(processed_dir)
            if used_auto_alpha:
                if can_write_exr:
                    self.parameter_output_values["status_message"] = (
                        "CorridorKey inference complete. Alpha hint was auto-generated from greenscreen (coarse mode)."
                    )
                else:
                    self.parameter_output_values["status_message"] = (
                        "CorridorKey inference complete. OpenEXR is unavailable in this OpenCV build, "
                        "so FG/Matte/Processed were saved as PNG."
                    )
            else:
                if can_write_exr:
                    self.parameter_output_values["status_message"] = "CorridorKey inference complete."
                else:
                    self.parameter_output_values["status_message"] = (
                        "CorridorKey inference complete. OpenEXR is unavailable in this OpenCV build, "
                        "so FG/Matte/Processed were saved as PNG."
                    )
        except Exception as exc:
            self._set_failure(f"CorridorKey inference failed: {exc}")
