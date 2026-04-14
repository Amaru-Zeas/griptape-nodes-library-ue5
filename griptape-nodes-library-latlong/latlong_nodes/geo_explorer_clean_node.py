"""Geo Explorer Clean node - minimal stable geo viewer + capture."""

from __future__ import annotations

import io
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlparse

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
GEO_EXPLORER_CLEAN_VERSION = "clean-v1.0.5"
CAPTURE_RATIO_CHOICES = ["16:9", "1:1", "9:16", "4:3", "3:2", "21:9"]
CAPTURE_RESOLUTION_CHOICES = ["1k", "2k", "4k"]
CAPTURE_LONG_SIDE_BY_PRESET = {"1k": 1280, "2k": 2048, "4k": 3840}


def _clean_mode(value: Any) -> str:
    mode = str(value or "earth").strip().lower()
    if mode in {"earth", "map", "street_view"}:
        return mode
    return "earth"


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


def _build_snapshot_url(
    mode: str,
    lat: float,
    lng: float,
    api_key: str,
    zoom: int = 15,
    heading: float = 0.0,
    pitch: float = 0.0,
) -> str:
    if mode == "street_view":
        if not api_key:
            return ""
        return (
            "https://maps.googleapis.com/maps/api/streetview"
            f"?size=1280x720&location={quote_plus(f'{lat:.6f},{lng:.6f}')}"
            f"&heading={heading:.1f}&pitch={pitch:.1f}&fov=80"
            f"&key={quote_plus(api_key)}"
        )

    if api_key:
        maptype = "satellite" if mode == "earth" else "roadmap"
        return (
            "https://maps.googleapis.com/maps/api/staticmap"
            f"?size=1280x720&center={quote_plus(f'{lat:.6f},{lng:.6f}')}"
            f"&zoom={max(1, int(zoom))}&maptype={maptype}"
            f"&markers=color:red%7C{quote_plus(f'{lat:.6f},{lng:.6f}')}"
            f"&key={quote_plus(api_key)}"
        )

    return (
        "https://staticmap.openstreetmap.de/staticmap.php"
        f"?center={lat:.6f},{lng:.6f}&zoom={max(1, int(zoom))}&size=1280x720"
        f"&markers={lat:.6f},{lng:.6f},red-pushpin"
    )


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
    w_ratio = max(1.0, float(w_raw))
    h_ratio = max(1.0, float(h_raw))
    ratio = w_ratio / h_ratio

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
    file_name = f"geo_clean_capture_{int(time.time() * 1000)}.{fmt}"
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


def _download_image_artifact(image_url: str, target_width: int = 0, target_height: int = 0) -> tuple[ImageArtifact | None, str, str, str]:
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
        if fmt not in {"png", "jpeg", "webp"}:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            raw = buf.getvalue()
            fmt = "png"

        if target_width > 0 and target_height > 0 and (width != target_width or height != target_height):
            fitted = ImageOps.fit(
                img.convert("RGB"),
                (int(target_width), int(target_height)),
                method=Image.Resampling.LANCZOS,
            )
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
    return ImageUrlArtifact(value=value, name="geo_clean_capture")


def _extract_street_camera(url: str) -> tuple[float, float]:
    """Best-effort heading/pitch extraction from live Street View URL."""
    if not url:
        return 0.0, 0.0
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query or "")
        heading = _to_float((qs.get("heading", ["0"])[0]), 0.0)
        pitch = _to_float((qs.get("pitch", ["0"])[0]), 0.0)

        # Some maps links encode camera in cbp, e.g. cbp=11,90,0,0,0
        cbp = unquote_plus((qs.get("cbp", [""])[0]) or "")
        if cbp:
            parts = [p.strip() for p in cbp.split(",")]
            if len(parts) >= 3:
                heading = _to_float(parts[1], heading)
                pitch = _to_float(parts[2], pitch)

        return heading, pitch
    except Exception:
        return 0.0, 0.0


class GeoExplorerCleanNode(DataNode):
    """Fresh simplified Geo Explorer node for stable GTN behavior."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "GeoExplorer",
            "description": "Clean geo explorer with stable street/map capture",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        self._last_capture_nonce = ""
        self._cached_capture_path = ""
        self._cached_capture_url = ""
        self._live_view_url = ""
        self._live_view_mode = "earth"
        self._live_view_query = ""

        self.add_parameter(
            Parameter(
                name="search_query",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Place, street, city, or lat,lng",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="latitude",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Fallback latitude",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="longitude",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Fallback longitude",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="mode",
                input_types=["str"],
                type="str",
                default_value="earth",
                tooltip="Viewer mode",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["earth", "map", "street_view"])},
            )
        )
        self.add_parameter(
            Parameter(
                name="api_key",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Google API key override for backend geocode/snapshot calls",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="capture_aspect_ratio",
                input_types=["str"],
                type="str",
                default_value="16:9",
                tooltip="Capture aspect ratio preset",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=CAPTURE_RATIO_CHOICES)},
            )
        )
        self.add_parameter(
            Parameter(
                name="capture_resolution",
                input_types=["str"],
                type="str",
                default_value="1k",
                tooltip="Capture resolution preset (long side)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=CAPTURE_RESOLUTION_CHOICES)},
            )
        )
        self.add_parameter(
            Parameter(
                name="street_heading",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Street View heading (degrees)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="street_pitch",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Street View pitch (degrees)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="viewer",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={
                    "url": "",
                    "mode": "earth",
                    "query": "",
                    "capture_nonce": "",
                    "node_version": GEO_EXPLORER_CLEAN_VERSION,
                },
                tooltip="Interactive geo viewer widget",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="GeoExplorerWidget", library="GTN LatLong Geo Library")},
            )
        )
        self.add_parameter(
            Parameter(
                name="capture_nonce",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Capture trigger nonce from widget",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="captured_image",
                output_type="ImageUrlArtifact",
                tooltip="Primary local capture output",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="node_version",
                output_type="str",
                tooltip="Geo Explorer Clean runtime version marker",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        with ParameterGroup(name="Outputs", collapsed=True) as outputs_group:
            Parameter(name="resolved_latitude", output_type="float", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="resolved_longitude", output_type="float", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="formatted_address", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="earth_url", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="map_url", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="street_view_url", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="current_url", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="captured_image_path", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="captured_image_url", output_type="str", allowed_modes={ParameterMode.OUTPUT})
            Parameter(name="status", output_type="str", allowed_modes={ParameterMode.OUTPUT})
        self.add_node_element(outputs_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "viewer" and isinstance(value, dict):
            mode = _clean_mode(value.get("mode", self.parameter_values.get("mode", "earth")))
            query = str(value.get("query", self.parameter_values.get("search_query", "")) or "").strip()
            url = str(value.get("url", "") or "").strip()
            self.parameter_values["mode"] = mode
            if query:
                self.parameter_values["search_query"] = query
            if url:
                self._live_view_url = url
                self._live_view_mode = mode
                self._live_view_query = query
            if value.get("capture_nonce"):
                self.parameter_values["capture_nonce"] = str(value.get("capture_nonce"))
            if "heading" in value:
                self.parameter_values["street_heading"] = _to_float(value.get("heading", 0.0))
            if "pitch" in value:
                self.parameter_values["street_pitch"] = _to_float(value.get("pitch", 0.0))
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

    def _geocode(self, query: str, api_key: str) -> tuple[float | None, float | None, str]:
        if api_key:
            try:
                response = requests.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": query, "key": api_key},
                    timeout=12,
                )
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results", []) if isinstance(payload, dict) else []
                if results:
                    first = results[0]
                    loc = first.get("geometry", {}).get("location", {})
                    return _to_float(loc.get("lat")), _to_float(loc.get("lng")), str(first.get("formatted_address", query))
            except Exception:
                pass
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": "GTN-LatLong-Geo-Library/clean-node"},
                timeout=12,
            )
            response.raise_for_status()
            results = response.json()
            if isinstance(results, list) and results:
                first = results[0]
                return _to_float(first.get("lat")), _to_float(first.get("lon")), str(first.get("display_name", query))
        except Exception:
            pass
        return None, None, ""

    @staticmethod
    def _build_urls(lat: float, lng: float, query: str, api_key: str, heading: float, pitch: float) -> dict[str, str]:
        clean_query = query.strip() if query.strip() else f"{lat:.6f},{lng:.6f}"
        encoded_query = quote_plus(clean_query)
        center_value = quote_plus(f"{lat:.6f},{lng:.6f}")

        if api_key:
            return {
                "earth_url": (
                    "https://www.google.com/maps/embed/v1/view"
                    f"?key={quote_plus(api_key)}&center={center_value}&zoom=15&maptype=satellite"
                ),
                "map_url": (
                    "https://www.google.com/maps/embed/v1/place"
                    f"?key={quote_plus(api_key)}&q={encoded_query}&zoom=15"
                ),
                "street_view_url": (
                    "https://www.google.com/maps/embed/v1/streetview"
                    f"?key={quote_plus(api_key)}&location={center_value}&heading={heading:.1f}&pitch={pitch:.1f}&fov=80"
                ),
            }

        return {
            "earth_url": f"https://maps.google.com/maps?q={encoded_query}&t=k&z=15&output=embed",
            "map_url": f"https://maps.google.com/maps?q={encoded_query}&z=15&output=embed",
            "street_view_url": (
                "https://maps.google.com/maps?layer=c"
                f"&cbll={lat:.6f},{lng:.6f}&cbp=11,{heading:.1f},{pitch:.1f},0,0&output=svembed"
            ),
        }

    def process(self) -> None:
        mode = _clean_mode(self.parameter_values.get("mode", "earth"))
        query = str(self.parameter_values.get("search_query", "") or "").strip()
        lat = _to_float(self.parameter_values.get("latitude", 0.0))
        lng = _to_float(self.parameter_values.get("longitude", 0.0))
        api_key = self._resolve_google_api_key()
        capture_aspect_ratio = _normalize_capture_ratio(self.parameter_values.get("capture_aspect_ratio", "16:9"))
        capture_resolution = _normalize_capture_resolution(self.parameter_values.get("capture_resolution", "1k"))
        capture_width, capture_height = _capture_dimensions(capture_aspect_ratio, capture_resolution)
        street_heading = _to_float(self.parameter_values.get("street_heading", 0.0))
        street_pitch = _to_float(self.parameter_values.get("street_pitch", 0.0))
        street_heading = street_heading % 360.0
        street_pitch = max(-89.0, min(89.0, street_pitch))
        status = ""

        if query:
            parsed = _parse_latlng(query)
            if parsed:
                lat, lng = parsed
                formatted_address = f"{lat:.6f}, {lng:.6f}"
                status = "Resolved from lat,lng input."
            else:
                rlat, rlng, address = self._geocode(query, api_key)
                if rlat is not None and rlng is not None:
                    lat, lng = rlat, rlng
                    formatted_address = address or query
                    status = "Resolved from place/street search."
                else:
                    formatted_address = query
                    status = "Could not geocode query. Using fallback coordinates."
        else:
            formatted_address = f"{lat:.6f}, {lng:.6f}"
            status = "Using latitude/longitude inputs."

        urls = self._build_urls(lat, lng, query, api_key, street_heading, street_pitch)
        current_url = urls["earth_url"]
        if mode == "map":
            current_url = urls["map_url"]
        elif mode == "street_view":
            current_url = urls["street_view_url"]

        # Preserve the exact in-widget URL between runs to avoid iframe reset.
        if self._live_view_url and mode == self._live_view_mode:
            current_url = self._live_view_url

        capture_nonce = str(self.parameter_values.get("capture_nonce", "") or "")
        should_capture = bool(capture_nonce and capture_nonce != self._last_capture_nonce)
        live_view_input = self.parameter_values.get("viewer", {})
        live_url_from_input = ""
        if isinstance(live_view_input, dict):
            live_url_from_input = str(live_view_input.get("url", "") or "").strip()
            if live_url_from_input:
                self._live_view_url = live_url_from_input
                self._live_view_mode = mode
                self._live_view_query = query

        captured_image_path = self._cached_capture_path
        captured_image_url = self._cached_capture_url
        captured_image_artifact = _build_url_artifact(captured_image_path, captured_image_url)
        snapshot_error = ""
        capture_heading = street_heading
        capture_pitch = street_pitch

        if should_capture:
            if mode == "street_view":
                extracted_h, extracted_p = _extract_street_camera(live_url_from_input or current_url)
                # Prefer explicit node/widget controls, but use extracted values when present.
                if abs(extracted_h) > 0.001 or abs(extracted_p) > 0.001:
                    capture_heading = extracted_h
                    capture_pitch = extracted_p
            snapshot_url = _build_snapshot_url(
                mode,
                lat,
                lng,
                api_key,
                zoom=15,
                heading=capture_heading,
                pitch=capture_pitch,
            )
            downloaded, path, static_url, snapshot_error = _download_image_artifact(
                snapshot_url,
                target_width=capture_width,
                target_height=capture_height,
            )
            if downloaded is not None:
                captured_image_path = path
                captured_image_url = static_url
                self._cached_capture_path = path
                self._cached_capture_url = static_url
                self._last_capture_nonce = capture_nonce
                captured_image_artifact = _build_url_artifact(path, static_url)
            elif mode == "street_view":
                captured_image_path = ""
                captured_image_url = ""
                captured_image_artifact = None

        self.parameter_output_values["resolved_latitude"] = lat
        self.parameter_output_values["resolved_longitude"] = lng
        self.parameter_output_values["formatted_address"] = formatted_address
        self.parameter_output_values["earth_url"] = urls["earth_url"]
        self.parameter_output_values["map_url"] = urls["map_url"]
        self.parameter_output_values["street_view_url"] = urls["street_view_url"]
        self.parameter_output_values["current_url"] = current_url
        self.parameter_output_values["captured_image"] = captured_image_artifact
        self.parameter_output_values["node_version"] = GEO_EXPLORER_CLEAN_VERSION
        self.parameter_output_values["captured_image_path"] = captured_image_path
        self.parameter_output_values["captured_image_url"] = captured_image_url

        if snapshot_error:
            status = f"{status} {snapshot_error}".strip()
        elif should_capture and captured_image_path:
            if mode == "street_view":
                status = (
                    f"{status} Capture saved: {captured_image_path} "
                    f"(h={capture_heading:.1f}, p={capture_pitch:.1f}, {capture_width}x{capture_height})"
                ).strip()
            else:
                status = f"{status} Capture saved: {captured_image_path} ({capture_width}x{capture_height})".strip()
        elif not should_capture:
            status = f"{status} Capture idle (click Capture button).".strip()

        viewer_payload = {
            "url": current_url,
            "mode": mode,
            "query": query or f"{lat:.6f},{lng:.6f}",
            "capture_nonce": capture_nonce,
            "node_version": GEO_EXPLORER_CLEAN_VERSION,
            "capture_aspect_ratio": capture_aspect_ratio,
            "capture_resolution": capture_resolution,
            "capture_width": capture_width,
            "capture_height": capture_height,
            "heading": street_heading,
            "pitch": street_pitch,
            "latitude": lat,
            "longitude": lng,
            "earth_url": urls["earth_url"],
            "map_url": urls["map_url"],
            "street_view_url": urls["street_view_url"],
        }
        self.parameter_output_values["status"] = f"{status} Node {GEO_EXPLORER_CLEAN_VERSION}".strip()
        self.parameter_output_values["viewer"] = viewer_payload
        self.parameter_values["viewer"] = viewer_payload

