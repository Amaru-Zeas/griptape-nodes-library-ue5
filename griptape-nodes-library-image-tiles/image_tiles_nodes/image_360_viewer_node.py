"""Simple 360 image viewer node for equirectangular images."""

from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Any

import requests
from PIL import Image
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget

DEFAULT_STATICFILES_DIR = Path(r"C:\Users\AI PC\GriptapeNodes\staticfiles")
HTTP_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
STATICFILES_RE = re.compile(r"/staticfiles/[^\s\"'<>]+", re.IGNORECASE)
WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^\"'\r\n]+")
VALUE_ASSIGN_RE = re.compile(r"value\s*=\s*(['\"])(.*?)\1", re.IGNORECASE)


def _candidate_paths(raw_path: str) -> list[Path]:
    text = str(raw_path or "").strip()
    if not text:
        return []

    normalized = text.replace("\\", "/")
    candidates: list[Path] = [Path(text)]
    if normalized.startswith("{inputs}/"):
        suffix = normalized[len("{inputs}/") :]
        candidates.append(Path.home() / "GriptapeNodes" / "inputs" / suffix)
    return candidates


def _is_http_url(text: str) -> bool:
    lower = text.lower().strip()
    return lower.startswith("http://") or lower.startswith("https://")


def _is_data_url(text: str) -> bool:
    return text.strip().lower().startswith("data:")


def _decode_data_url(data_url: str) -> bytes:
    if "," not in data_url:
        msg = "Invalid data URL format."
        raise ValueError(msg)
    _, b64 = data_url.split(",", 1)
    return base64.b64decode(b64)


def _extract_string_candidate(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
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
            if isinstance(parsed, dict):
                for k in ("image_url", "url", "path", "value", "image_data", "image_data_url"):
                    if k in parsed:
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
        return text[text.find("data:") :]
    for regex in (HTTP_RE, STATICFILES_RE, WIN_PATH_RE):
        match = regex.search(text)
        if match:
            return match.group(0)
    return text


def _image_bytes_to_preview_data_url(image_bytes: bytes, max_width: int = 4096) -> str:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if max_width > 0 and img.width > max_width:
        new_height = max(1, int(round(img.height * (max_width / float(img.width)))))
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + b64


def _download_http_image_as_data_url(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        if not resp.content:
            return ""
        return _image_bytes_to_preview_data_url(resp.content)
    except Exception:
        return ""


def _staticfiles_url_to_data_url(url: str) -> str:
    text = str(url or "").strip()
    if not text.startswith("/staticfiles/"):
        return ""
    file_name = text.split("/staticfiles/", 1)[1].strip().lstrip("/")
    if not file_name:
        return ""
    static_dir = Path(os.environ.get("GTN_STATICFILES_DIR", str(DEFAULT_STATICFILES_DIR)))
    path = static_dir / file_name
    if path.exists() and path.is_file():
        try:
            return _image_bytes_to_preview_data_url(path.read_bytes())
        except Exception:
            return ""
    return ""


def _resolve_image_sources(value: Any, depth: int = 0) -> tuple[str, str]:
    """Return tuple of (image_url, image_data_url)."""
    if depth > 8:
        return "", ""
    if value is None:
        return "", ""

    if isinstance(value, bytes):
        return "", _image_bytes_to_preview_data_url(value)

    if isinstance(value, (list, tuple, set)):
        for item in value:
            resolved_url, resolved_data_url = _resolve_image_sources(item, depth + 1)
            if resolved_url or resolved_data_url:
                return resolved_url, resolved_data_url
        return "", ""

    if isinstance(value, str):
        raw = _extract_string_candidate(value)
        if not raw:
            return "", ""
        if _is_http_url(raw):
            # Prefer data URL for reliability (avoids CORS/auth/network edge cases in widget).
            data_url = _download_http_image_as_data_url(raw)
            return (raw, data_url) if data_url else (raw, "")
        if _is_data_url(raw):
            return "", raw
        if raw.startswith("/staticfiles/"):
            # Keep as fallback URL, but prefer local file bytes when available.
            data_url = _staticfiles_url_to_data_url(raw)
            return (raw, data_url) if data_url else (raw, "")
        for path in _candidate_paths(raw):
            if path.exists() and path.is_file():
                return "", _image_bytes_to_preview_data_url(path.read_bytes())
        return "", ""

    if isinstance(value, dict):
        for key in ("image_url", "url", "path", "value", "image_data", "image_data_url", "base64", "b64_json"):
            candidate = value.get(key)
            if candidate is not None:
                resolved_url, resolved_data_url = _resolve_image_sources(candidate, depth + 1)
                if resolved_url or resolved_data_url:
                    return resolved_url, resolved_data_url
        for candidate in value.values():
            resolved_url, resolved_data_url = _resolve_image_sources(candidate, depth + 1)
            if resolved_url or resolved_data_url:
                return resolved_url, resolved_data_url
        return "", ""

    raw_value = getattr(value, "value", None)
    if raw_value is not None:
        resolved_url, resolved_data_url = _resolve_image_sources(raw_value, depth + 1)
        if resolved_url or resolved_data_url:
            return resolved_url, resolved_data_url

    raw_path = getattr(value, "path", None)
    if raw_path is not None:
        resolved_url, resolved_data_url = _resolve_image_sources(raw_path, depth + 1)
        if resolved_url or resolved_data_url:
            return resolved_url, resolved_data_url

    raw_url = getattr(value, "url", None)
    if raw_url is not None:
        resolved_url, resolved_data_url = _resolve_image_sources(raw_url, depth + 1)
        if resolved_url or resolved_data_url:
            return resolved_url, resolved_data_url

    return "", ""


class Image360ViewerNode(DataNode):
    """Render an equirectangular image in an interactive 360 sphere viewer."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "ImageTiles",
            "description": "Preview a 2:1 equirectangular image in an interactive 360 viewer.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        self.set_initial_node_size(width=980, height=760)

        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str", "dict"],
                type="ImageUrlArtifact",
                tooltip="Equirectangular image input (2:1 recommended).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="hfov",
                input_types=["int"],
                type="int",
                default_value=95,
                tooltip="Initial horizontal field of view (smaller = zoom in).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="viewer_state",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={"image_url": "", "image_data_url": "", "hfov": 95},
                tooltip="Internal widget state for the 360 image viewer.",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="Image360ViewerWidget", library="Image Tiles Library")},
            )
        )
        self.add_parameter(
            Parameter(
                name="resolved_image_url",
                output_type="str",
                tooltip="Resolved URL used by the 360 viewer widget.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        image_value = self.parameter_values.get("image")
        image_url, image_data_url = _resolve_image_sources(image_value)

        hfov_raw = int(self.parameter_values.get("hfov") or 95)
        hfov = max(40, min(140, hfov_raw))

        state = {
            "image_url": image_url,
            "image_data_url": image_data_url,
            "hfov": hfov,
        }

        self.parameter_output_values["viewer_state"] = state
        self.parameter_output_values["resolved_image_url"] = image_url
