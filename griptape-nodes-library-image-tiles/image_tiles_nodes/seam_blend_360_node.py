from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import requests
from PIL import Image, ImageFilter
from griptape.artifacts import ImageArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.options import Options

DEFAULT_STATICFILES_DIR = Path(r"C:\Users\AI PC\GriptapeNodes\staticfiles")
HTTP_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
STATICFILES_RE = re.compile(r"/staticfiles/[^\s\"'<>]+", re.IGNORECASE)
WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^\"'\r\n]+")
VALUE_ASSIGN_RE = re.compile(r"value\s*=\s*(['\"])(.*?)\1", re.IGNORECASE)


def _decode_data_url(data_url: str) -> bytes:
    if not isinstance(data_url, str) or "," not in data_url:
        raise ValueError("Invalid data URL image input.")
    _, b64_data = data_url.split(",", 1)
    return base64.b64decode(b64_data)


def _is_http_url(text: str) -> bool:
    lower = str(text or "").strip().lower()
    return lower.startswith("http://") or lower.startswith("https://")


def _candidate_paths(raw_path: str) -> list[Path]:
    text = str(raw_path or "").strip()
    if not text:
        return []
    normalized = text.replace("\\", "/")
    candidates: list[Path] = [Path(text)]
    if normalized.startswith("{inputs}/"):
        suffix = normalized[len("{inputs}/") :]
        candidates.append(Path.home() / "GriptapeNodes" / "inputs" / suffix)
    if normalized.startswith("/staticfiles/"):
        file_name = normalized.split("/staticfiles/", 1)[1].strip().lstrip("/")
        if file_name:
            static_dir = Path(os.environ.get("GTN_STATICFILES_DIR", str(DEFAULT_STATICFILES_DIR)))
            candidates.append(static_dir / file_name)
    return candidates


def _download_http_image_bytes(url: str) -> bytes | None:
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        if not resp.content:
            return None
        return resp.content
    except Exception:
        return None


def _extract_string_candidate(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    # Normalize common escaped forms seen in serialized artifact payloads.
    text = text.replace("\\/", "/").replace("\\\\", "\\")
    if text.startswith(("'", '"')) and text.endswith(("'", '"')) and len(text) >= 2:
        text = text[1:-1].strip()
    if text.startswith("data:"):
        return text
    if text.startswith("file://"):
        return text.replace("file:///", "").replace("file://", "")
    if _is_http_url(text) or text.startswith("/staticfiles/"):
        return text
    if any(ch in text for ch in ("{", "[")):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (dict, list, tuple)):
                for k in ("value", "url", "path", "image", "image_url", "image_data", "image_data_url"):
                    if isinstance(parsed, dict) and k in parsed:
                        candidate = _extract_string_candidate(str(parsed.get(k) or ""))
                        if candidate:
                            return candidate
        except Exception:
            pass
    value_match = VALUE_ASSIGN_RE.search(text)
    if value_match:
        candidate = _extract_string_candidate(value_match.group(2))
        if candidate:
            return candidate
    if "data:" in text:
        start = text.find("data:")
        return text[start:]
    for regex in (HTTP_RE, STATICFILES_RE, WIN_PATH_RE):
        match = regex.search(text)
        if match:
            return match.group(0)
    return text


def _read_image_bytes(value: Any, depth: int = 0) -> bytes:
    if depth > 8:
        raise ValueError("Image input nesting too deep.")
    if value is None:
        raise ValueError("No image input provided.")
    if isinstance(value, bytes):
        return value
    if isinstance(value, (list, tuple, set)):
        for item in value:
            try:
                return _read_image_bytes(item, depth + 1)
            except Exception:
                continue
        raise ValueError("Iterable image input did not contain supported image data.")
    if isinstance(value, str):
        candidate = _extract_string_candidate(value)
        if candidate.startswith("data:"):
            return _decode_data_url(candidate)
        if _is_http_url(candidate):
            downloaded = _download_http_image_bytes(candidate)
            if downloaded is not None:
                return downloaded
        for path in _candidate_paths(candidate):
            if path.exists() and path.is_file():
                return path.read_bytes()
        raise ValueError("String image input is not a valid data URL, HTTP URL, staticfiles URL, or local file path.")
    if isinstance(value, dict):
        for key in ("value", "image", "image_data", "image_data_url", "url", "path", "base64", "b64_json"):
            candidate = value.get(key)
            if candidate is not None:
                return _read_image_bytes(candidate, depth + 1)
        for candidate in value.values():
            try:
                return _read_image_bytes(candidate, depth + 1)
            except Exception:
                continue
        raise ValueError("Dict image input did not contain a supported image field.")
    raw_value = getattr(value, "value", None)
    if raw_value is not None:
        return _read_image_bytes(raw_value, depth + 1)
    raw_url = getattr(value, "url", None)
    if raw_url is not None:
        return _read_image_bytes(raw_url, depth + 1)
    raw_path = getattr(value, "path", None)
    if raw_path is not None:
        return _read_image_bytes(raw_path, depth + 1)
    raw_b64 = getattr(value, "base64", None)
    if isinstance(raw_b64, str) and raw_b64:
        if raw_b64.startswith("data:"):
            return _decode_data_url(raw_b64)
        return base64.b64decode(raw_b64)
    raise ValueError(f"Unsupported image input type: {type(value).__name__}")


def _blend_curve(mode: str, width: int) -> np.ndarray:
    if width <= 0:
        return np.zeros((0,), dtype=np.float32)
    t = np.linspace(0.0, 1.0, width, dtype=np.float32)
    if mode == "cosine":
        curve = 0.5 * (1.0 - np.cos(np.pi * t))
    elif mode == "smooth":
        curve = t * t * (3.0 - 2.0 * t)
    else:
        curve = t
    return np.clip(curve, 0.0, 1.0)


def _blend_edges(np_img: np.ndarray, blend_width: int, mode: str) -> np.ndarray:
    _, w = np_img.shape[:2]
    bw = max(0, min(blend_width, w // 2))
    if bw == 0:
        return np_img

    out = np_img.astype(np.float32).copy()
    left = out[:, :bw, :]
    right_from_seam = out[:, w - bw :, :][:, ::-1, :]

    seam_strength = (1.0 - _blend_curve(mode, bw)).reshape(1, bw, 1)
    seam_average = 0.5 * (left + right_from_seam)
    left_new = left * (1.0 - seam_strength) + seam_average * seam_strength
    right_new = right_from_seam * (1.0 - seam_strength) + seam_average * seam_strength

    out[:, :bw, :] = left_new
    out[:, w - bw :, :] = right_new[:, ::-1, :]
    return np.clip(out, 0.0, 255.0).astype(np.uint8)


def _apply_seam_blur(np_img: np.ndarray, seam_width: int, blur_radius: int, blur_mix: float, mode: str) -> np.ndarray:
    h, w = np_img.shape[:2]
    if seam_width <= 0 or blur_radius <= 0 or blur_mix <= 0.0:
        return np_img

    blur_width = max(1, min(seam_width, w // 2))
    mix = float(np.clip(blur_mix, 0.0, 1.0))
    curve = _blend_curve(mode, blur_width)
    seam_strength = 1.0 - curve

    mask = np.zeros((h, w, 1), dtype=np.float32)
    mask[:, :blur_width, 0] = seam_strength
    mask[:, w - blur_width :, 0] = seam_strength[::-1]
    mask *= mix

    blurred = np.array(Image.fromarray(np_img, mode="RGB").filter(ImageFilter.GaussianBlur(radius=blur_radius))).astype(
        np.float32
    )
    base = np_img.astype(np.float32)
    out = base * (1.0 - mask) + blurred * mask
    return np.clip(out, 0.0, 255.0).astype(np.uint8)


class SeamBlend360Node(DataNode):
    """Blend left/right panorama edges for seamless wraparound."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "ImageTiles",
            "description": "Blend left and right panorama edges to reduce visible seams.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str", "dict"],
                type="ImageArtifact",
                tooltip="Input equirectangular image.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="blend_width",
                input_types=["int"],
                type="int",
                default_value=16,
                tooltip="Number of pixels to blend at both horizontal edges.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="blend_mode",
                input_types=["str"],
                type="str",
                default_value="cosine",
                traits={Options(choices=["cosine", "linear", "smooth"])},
                tooltip="Blend curve type.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="seam_blur_radius",
                input_types=["int"],
                type="int",
                default_value=2,
                tooltip="Optional Gaussian blur radius applied only near seam edges. Set 0 to disable.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="seam_blur_mix",
                input_types=["float"],
                type="float",
                default_value=0.35,
                tooltip="How much seam-only blur is mixed in (0.0-1.0).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="Seam-blended panorama image.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="width",
                output_type="int",
                tooltip="Output image width.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="height",
                output_type="int",
                tooltip="Output image height.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="aspect_ratio",
                output_type="float",
                tooltip="Output width/height ratio.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        image_value = self.parameter_values.get("image")
        blend_width = int(self.parameter_values.get("blend_width") or 16)
        blend_mode = str(self.parameter_values.get("blend_mode") or "cosine").strip().lower()
        seam_blur_radius = max(0, int(self.parameter_values.get("seam_blur_radius") or 0))
        seam_blur_mix = float(self.parameter_values.get("seam_blur_mix") or 0.0)
        if blend_mode not in {"cosine", "linear", "smooth"}:
            blend_mode = "cosine"

        image_bytes = _read_image_bytes(image_value)
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = pil_image.size

        np_img = np.array(pil_image)
        np_blended = _blend_edges(np_img, blend_width, blend_mode)
        np_blended = _apply_seam_blur(
            np_blended,
            seam_width=max(1, blend_width),
            blur_radius=seam_blur_radius,
            blur_mix=seam_blur_mix,
            mode=blend_mode,
        )

        out_img = Image.fromarray(np_blended, mode="RGB")
        out_buf = io.BytesIO()
        out_img.save(out_buf, format="PNG")
        out_bytes = out_buf.getvalue()

        artifact = ImageArtifact(
            value=out_bytes,
            width=width,
            height=height,
            format="png",
            name=f"{self.name}_blended.png",
        )

        self.parameter_output_values["output_image"] = artifact
        self.parameter_output_values["width"] = width
        self.parameter_output_values["height"] = height
        self.parameter_output_values["aspect_ratio"] = float(width) / max(float(height), 1.0)

