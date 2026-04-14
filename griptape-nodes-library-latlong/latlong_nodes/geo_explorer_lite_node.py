"""Geo Explorer Lite node - very simple satellite/photo viewer with capture."""

from __future__ import annotations

import io
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image, ImageOps

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.widget import Widget

GOOGLE_API_KEY_SECRET = "GOOGLE_MAPS_API_KEY"
DEFAULT_STATICFILES_DIR = Path(r"C:\Users\AI PC\GriptapeNodes\staticfiles")
LATLNG_PATTERN = re.compile(r"^\s*([+-]?\d{1,2}(?:\.\d+)?)\s*,\s*([+-]?\d{1,3}(?:\.\d+)?)\s*$")
LITE_VERSION = "lite-v1.0.2"
MODE_CHOICES = ["satellite", "photo"]
CAPTURE_RATIO_CHOICES = ["16:9", "1:1", "9:16", "4:3", "3:2", "21:9"]
CAPTURE_RESOLUTION_CHOICES = ["1k", "2k", "4k"]
CAPTURE_LONG_SIDE_BY_PRESET = {"1k": 1280, "2k": 2048, "4k": 3840}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_latlng(text: str) -> tuple[float, float] | None:
    match = LATLNG_PATTERN.match(text or "")
    if not match:
        return None
    lat = float(match.group(1))
    lng = float(match.group(2))
    if lat < -90.0 or lat > 90.0 or lng < -180.0 or lng > 180.0:
        return None
    return lat, lng


def _normalize_mode(value: Any) -> str:
    mode = str(value or "satellite").strip().lower()
    return mode if mode in MODE_CHOICES else "satellite"


def _normalize_capture_ratio(value: Any) -> str:
    raw = str(value or "16:9").strip()
    return raw if raw in CAPTURE_RATIO_CHOICES else "16:9"


def _normalize_capture_resolution(value: Any) -> str:
    raw = str(value or "1k").strip().lower()
    return raw if raw in CAPTURE_RESOLUTION_CHOICES else "1k"


def _capture_dimensions(aspect_ratio: str, resolution_preset: str) -> tuple[int, int]:
    ratio_text = _normalize_capture_ratio(aspect_ratio)
    resolution_text = _normalize_capture_resolution(resolution_preset)
    long_side = CAPTURE_LONG_SIDE_BY_PRESET.get(resolution_text, 1280)
    w_raw, h_raw = ratio_text.split(":", 1)
    ratio = max(1.0, float(w_raw)) / max(1.0, float(h_raw))
    if ratio >= 1.0:
        width = long_side
        height = int(round(long_side / ratio))
    else:
        height = long_side
        width = int(round(long_side * ratio))
    if width % 2:
        width += 1
    if height % 2:
        height += 1
    return max(320, width), max(240, height)


def _build_artifact_and_save(raw: bytes, width: int, height: int, fmt: str) -> tuple[ImageArtifact, str, str]:
    file_name = f"geo_lite_capture_{int(time.time() * 1000)}.{fmt}"
    static_dir = Path(os.environ.get("GTN_STATICFILES_DIR", str(DEFAULT_STATICFILES_DIR)))
    static_path = ""
    static_url = ""
    try:
        static_dir.mkdir(parents=True, exist_ok=True)
        out_path = static_dir / file_name
        with out_path.open("wb") as f:
            f.write(raw)
        static_path = str(out_path)
        static_url = f"/staticfiles/{file_name}"
    except Exception:
        pass
    return ImageArtifact(value=raw, width=width, height=height, format=fmt, name=file_name), static_path, static_url


def _download_image_artifact(image_url: str, target_width: int, target_height: int) -> tuple[ImageArtifact | None, str, str, str]:
    if not image_url:
        return None, "", "", "No snapshot URL available."
    try:
        response = requests.get(image_url, timeout=20)
        response.raise_for_status()
        raw = response.content
        if not raw:
            return None, "", "", "Snapshot request returned empty image content."
        img = Image.open(io.BytesIO(raw))
        width, height = img.size
        fmt = (img.format or "PNG").lower()
        if fmt == "jpg":
            fmt = "jpeg"
        if target_width > 0 and target_height > 0 and (width != target_width or height != target_height):
            fitted = ImageOps.fit(img.convert("RGB"), (target_width, target_height), method=Image.Resampling.LANCZOS)
            out = io.BytesIO()
            fitted.save(out, format="PNG")
            raw = out.getvalue()
            width, height = fitted.size
            fmt = "png"
        artifact, static_path, static_url = _build_artifact_and_save(raw, width, height, fmt)
        return artifact, static_path, static_url, ""
    except Exception as exc:
        return None, "", "", f"Snapshot download failed: {exc}"


def _build_url_artifact(path: str, static_url: str) -> ImageUrlArtifact | None:
    value = (path or "").strip() or (static_url or "").strip()
    if not value:
        return None
    return ImageUrlArtifact(value=value, name="geo_lite_capture")


class GeoExplorerLiteNode(DataNode):
    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "GeoExplorer",
            "description": "Simple satellite + photo view with capture.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        self._last_capture_nonce = ""
        self._cached_capture_path = ""
        self._cached_capture_url = ""

        self.add_parameter(Parameter(name="search_query", input_types=["str"], type="str", default_value="", allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="latitude", input_types=["float"], type="float", default_value=0.0, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="longitude", input_types=["float"], type="float", default_value=0.0, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(
            Parameter(
                name="mode",
                input_types=["str"],
                type="str",
                default_value="satellite",
                traits={Options(choices=MODE_CHOICES)},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(Parameter(name="api_key", input_types=["str"], type="str", default_value="", allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(
            Parameter(
                name="capture_aspect_ratio",
                input_types=["str"],
                type="str",
                default_value="16:9",
                traits={Options(choices=CAPTURE_RATIO_CHOICES)},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="capture_resolution",
                input_types=["str"],
                type="str",
                default_value="1k",
                traits={Options(choices=CAPTURE_RESOLUTION_CHOICES)},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(Parameter(name="street_heading", input_types=["float"], type="float", default_value=0.0, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="street_pitch", input_types=["float"], type="float", default_value=0.0, allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(
            Parameter(
                name="viewer",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={"mode": "satellite", "query": "", "capture_nonce": "", "node_version": LITE_VERSION},
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="GeoExplorerLiteWidget", library="GTN LatLong Geo Library")},
            )
        )
        self.add_parameter(Parameter(name="capture_nonce", input_types=["str"], type="str", default_value="", allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self.add_parameter(Parameter(name="captured_image", output_type="ImageUrlArtifact", allowed_modes={ParameterMode.OUTPUT}))
        self.add_parameter(Parameter(name="node_version", output_type="str", allowed_modes={ParameterMode.OUTPUT}))

        with ParameterGroup(name="Outputs", collapsed=True) as grp:
            Parameter(name="resolved_latitude", output_type="float", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="resolved_longitude", output_type="float", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="captured_image_path", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="captured_image_url", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="status", output_type="str", allowed_modes={ParameterMode.OUTPUT})
        self.add_node_element(grp)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "viewer" and isinstance(value, dict):
            self.parameter_values["mode"] = _normalize_mode(value.get("mode", self.parameter_values.get("mode", "satellite")))
            q = str(value.get("query", self.parameter_values.get("search_query", "")) or "").strip()
            if q:
                self.parameter_values["search_query"] = q
            self.parameter_values["latitude"] = _to_float(value.get("latitude", self.parameter_values.get("latitude", 0.0)))
            self.parameter_values["longitude"] = _to_float(value.get("longitude", self.parameter_values.get("longitude", 0.0)))
            self.parameter_values["street_heading"] = _to_float(value.get("heading", self.parameter_values.get("street_heading", 0.0)))
            self.parameter_values["street_pitch"] = _to_float(value.get("pitch", self.parameter_values.get("street_pitch", 0.0)))
            if value.get("capture_nonce"):
                self.parameter_values["capture_nonce"] = str(value.get("capture_nonce"))
        return super().after_value_set(parameter, value)

    def _resolve_google_api_key(self) -> str:
        direct = str(self.parameter_values.get("api_key", "") or "").strip()
        if direct:
            return direct
        env_value = os.getenv(GOOGLE_API_KEY_SECRET, "").strip()
        if env_value:
            return env_value
        try:
            secret = GriptapeNodes.SecretsManager().get_secret(GOOGLE_API_KEY_SECRET)
            if isinstance(secret, str) and secret.strip():
                return secret.strip()
        except Exception:
            pass
        return ""

    def _geocode(self, query: str, api_key: str) -> tuple[float | None, float | None]:
        if api_key:
            try:
                response = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params={"address": query, "key": api_key}, timeout=12)
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results", []) if isinstance(payload, dict) else []
                if results:
                    loc = results[0].get("geometry", {}).get("location", {})
                    return _to_float(loc.get("lat")), _to_float(loc.get("lng"))
            except Exception:
                pass
        return None, None

    def process(self) -> None:
        mode = _normalize_mode(self.parameter_values.get("mode", "satellite"))
        query = str(self.parameter_values.get("search_query", "") or "").strip()
        lat = _to_float(self.parameter_values.get("latitude", 0.0))
        lng = _to_float(self.parameter_values.get("longitude", 0.0))
        heading = _to_float(self.parameter_values.get("street_heading", 0.0)) % 360.0
        pitch = max(-89.0, min(89.0, _to_float(self.parameter_values.get("street_pitch", 0.0))))
        api_key = self._resolve_google_api_key()
        capture_ratio = _normalize_capture_ratio(self.parameter_values.get("capture_aspect_ratio", "16:9"))
        capture_res = _normalize_capture_resolution(self.parameter_values.get("capture_resolution", "1k"))
        cap_w, cap_h = _capture_dimensions(capture_ratio, capture_res)

        if query:
            parsed = _parse_latlng(query)
            if parsed:
                lat, lng = parsed
            else:
                glat, glng = self._geocode(query, api_key)
                if glat is not None and glng is not None:
                    lat, lng = glat, glng

        capture_nonce = str(self.parameter_values.get("capture_nonce", "") or "")
        should_capture = bool(capture_nonce and capture_nonce != self._last_capture_nonce)

        captured_path = self._cached_capture_path
        captured_url = self._cached_capture_url
        captured_artifact = _build_url_artifact(captured_path, captured_url)
        snapshot_error = ""

        if mode == "photo":
            snapshot_url = (
                "https://maps.googleapis.com/maps/api/streetview"
                f"?size=1280x720&location={quote_plus(f'{lat:.6f},{lng:.6f}')}"
                f"&heading={heading:.1f}&pitch={pitch:.1f}&fov=80"
                f"&key={quote_plus(api_key)}"
                if api_key
                else ""
            )
        else:
            snapshot_url = (
                "https://maps.googleapis.com/maps/api/staticmap"
                f"?size=1280x720&center={quote_plus(f'{lat:.6f},{lng:.6f}')}&zoom=15&maptype=satellite"
                f"&markers=color:red%7C{quote_plus(f'{lat:.6f},{lng:.6f}')}&key={quote_plus(api_key)}"
                if api_key
                else f"https://staticmap.openstreetmap.de/staticmap.php?center={lat:.6f},{lng:.6f}&zoom=15&size=1280x720&markers={lat:.6f},{lng:.6f},red-pushpin"
            )

        if should_capture:
            downloaded, path, static_url, snapshot_error = _download_image_artifact(snapshot_url, cap_w, cap_h)
            if downloaded is not None:
                captured_path = path
                captured_url = static_url
                self._cached_capture_path = path
                self._cached_capture_url = static_url
                self._last_capture_nonce = capture_nonce
                captured_artifact = _build_url_artifact(path, static_url)
            elif mode == "photo":
                captured_artifact = None
                captured_path = ""
                captured_url = ""

        query_value = query.strip() if query.strip() else f"{lat:.6f},{lng:.6f}"
        encoded_query = quote_plus(query_value)
        satellite_url = f"https://maps.google.com/maps?q={encoded_query}&t=k&z=15&output=embed"
        photo_url = f"https://maps.google.com/maps?q={encoded_query}&z=18&output=embed"
        current_url = photo_url if mode == "photo" else satellite_url

        viewer_state = {
            "mode": mode,
            "query": query or f"{lat:.6f},{lng:.6f}",
            "url": current_url,
            "satellite_url": satellite_url,
            "photo_url": photo_url,
            "capture_nonce": capture_nonce,
            "latitude": lat,
            "longitude": lng,
            "heading": heading,
            "pitch": pitch,
            "api_key": api_key,
            "node_version": LITE_VERSION,
        }

        status = f"Simple mode: {mode}. "
        if snapshot_error:
            status += snapshot_error
        elif should_capture and captured_path:
            status += f"Capture saved: {captured_path} ({cap_w}x{cap_h})"
        else:
            status += "Capture idle (click Capture then Run)."

        self.parameter_output_values["captured_image"] = captured_artifact
        self.parameter_output_values["node_version"] = LITE_VERSION
        self.parameter_output_values["resolved_latitude"] = lat
        self.parameter_output_values["resolved_longitude"] = lng
        self.parameter_output_values["captured_image_path"] = captured_path
        self.parameter_output_values["captured_image_url"] = captured_url
        self.parameter_output_values["status"] = status
        self.parameter_output_values["viewer"] = viewer_state
        self.parameter_values["viewer"] = viewer_state

