"""Media Store Set node."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

import media_store_registry as _registry


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return "data:application/octet-stream;base64," + base64.b64encode(value).decode("ascii")
    if isinstance(value, dict):
        for field in ("value", "url", "image_data_url", "video_url", "audio_url", "text"):
            raw = value.get(field)
            if isinstance(raw, str) and raw:
                return raw
        try:
            return json.dumps(value, ensure_ascii=True)
        except Exception:
            return str(value)

    raw_value = getattr(value, "value", None)
    if isinstance(raw_value, str) and raw_value:
        return raw_value

    raw_url = getattr(value, "url", None)
    if isinstance(raw_url, str) and raw_url:
        return raw_url

    raw_b64 = getattr(value, "base64", None)
    if isinstance(raw_b64, str) and raw_b64:
        if raw_b64.startswith("data:"):
            return raw_b64
        return "data:application/octet-stream;base64," + raw_b64

    return str(value)


def _infer_media_type(raw: Any, normalized: str) -> str:
    class_name = raw.__class__.__name__.lower() if raw is not None else ""
    if "image" in class_name:
        return "image"
    if "video" in class_name:
        return "video"
    if "audio" in class_name:
        return "audio"
    if "text" in class_name:
        return "text"

    s = (normalized or "").strip().lower()
    if s.startswith("data:image/"):
        return "image"
    if s.startswith("data:video/"):
        return "video"
    if s.startswith("data:audio/"):
        return "audio"

    parsed = urlparse(s)
    path = parsed.path if parsed.scheme else s
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")):
        return "image"
    if path.endswith((".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v")):
        return "video"
    if path.endswith((".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac")):
        return "audio"
    return "text"


def _name_from_value(raw: Any, normalized: str) -> str:
    def _is_hash_like(text: str) -> bool:
        t = text.strip()
        return len(t) >= 24 and all(ch in "0123456789abcdefABCDEF" for ch in t)

    def _stem_from_candidate(candidate: str) -> str:
        c = (candidate or "").strip()
        if not c or c.startswith("data:"):
            return ""
        parsed = urlparse(c)
        path = parsed.path if parsed.scheme else c
        base = Path(path).name.strip()
        if not base:
            return ""
        stem = Path(base).stem.strip() or base
        if _is_hash_like(stem):
            return ""
        return stem

    # Prefer actual file path/url name first (more user-friendly than artifact IDs).
    s = (normalized or "").strip()
    stem = _stem_from_candidate(s)
    if stem:
        return stem

    for attr_name in ("path", "file_path", "filename", "url", "value", "name"):
        attr_val = getattr(raw, attr_name, None)
        if isinstance(attr_val, str):
            stem = _stem_from_candidate(attr_val)
            if stem:
                return stem

    if isinstance(raw, dict):
        for field_name in ("path", "file_path", "filename", "url", "value", "name"):
            field_val = raw.get(field_name)
            if isinstance(field_val, str):
                stem = _stem_from_candidate(field_val)
                if stem:
                    return stem

    return ""


class MediaStoreSetNode(ControlNode):
    """Store text/media by key for later retrieval."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "MediaStore",
            "description": "Store text/image/video/audio value by key",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        register_fn = getattr(_registry, "register_set_node", None)
        if callable(register_fn):
            register_fn(self.name, self)

        self.add_parameter(
            Parameter(
                name="slot_name",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Dropdown key shown in Media Store Get. Leave empty to use this node name.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="media_name",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="If enabled, slot_name auto-uses media filename and overrides manual slot name edits.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="value",
                input_types=[
                    "str",
                    "dict",
                    "ImageArtifact",
                    "ImageUrlArtifact",
                    "VideoArtifact",
                    "VideoUrlArtifact",
                    "AudioArtifact",
                    "AudioUrlArtifact",
                    "TextArtifact",
                ],
                type="str",
                tooltip="Any text/media value (artifact, URL/path, data URL, or plain text).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

    def process(self) -> None:
        incoming = self.parameter_values.get("value")
        normalized = _string_value(incoming)
        key = self._resolve_key(incoming, normalized)
        media_type = _infer_media_type(incoming, normalized)

        _registry.upsert_entry(key=key, media_type=media_type, value=normalized, source_node=self.name)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in {"slot_name", "value", "media_name"}:
            incoming = self.parameter_values.get("value")
            normalized = _string_value(incoming)
            key = self._resolve_key(incoming, normalized)
            media_type = _infer_media_type(incoming, normalized)
            _registry.upsert_entry(key=key, media_type=media_type, value=normalized, source_node=self.name)
            if parameter.name == "media_name" and bool(value):
                # Force immediate UI sync attempt when toggle turns on.
                self._resolve_key(incoming, normalized)
        return super().after_value_set(parameter, value)

    def export_entry(self) -> dict[str, str]:
        incoming = self.parameter_values.get("value")
        normalized = _string_value(incoming)
        key = self._resolve_key(incoming, normalized)
        media_type = _infer_media_type(incoming, normalized)
        return {
            "key": key,
            "media_type": media_type,
            "value": normalized,
            "source_node": self.name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _resolve_key(self, incoming: Any, normalized: str) -> str:
        use_media_name = bool(self.parameter_values.get("media_name", False))
        if use_media_name:
            derived = _name_from_value(incoming, normalized).strip()
            if derived:
                # Keep slot_name synced and effectively non-editable while toggle is enabled.
                self.parameter_values["slot_name"] = derived
                return derived
        return str(self.parameter_values.get("slot_name", "") or "").strip() or self.name

