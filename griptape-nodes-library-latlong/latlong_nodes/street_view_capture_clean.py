"""Street View Capture Clean node - minimal stable Street View image capture."""

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
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

GOOGLE_API_KEY_SECRET = "GOOGLE_MAPS_API_KEY"
DEFAULT_STATICFILES_DIR = Path(r"C:\Users\AI PC\GriptapeNodes\staticfiles")
LATLNG_PATTERN = re.compile(r"^\s*([+-]?\d{1,2}(?:\.\d+)?)\s*,\s*([+-]?\d{1,3}(?:\.\d+)?)\s*$")


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


class StreetViewCaptureCleanNode(DataNode):
    """Clean Street View capture node with minimal inputs and local image output."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "GeoExplorer",
            "description": "Minimal Street View capture to local file and ImageUrlArtifact",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="search_query",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Place/street text or lat,lng pair",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="latitude",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Fallback latitude when search_query is empty",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="longitude",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Fallback longitude when search_query is empty",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="api_key",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Google API key (optional override of GOOGLE_MAPS_API_KEY secret)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="captured_image",
                output_type="ImageUrlArtifact",
                tooltip="Saved Street View image for Display Image.image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="captured_image_path",
                output_type="str",
                tooltip="Local saved file path",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="captured_image_url",
                output_type="str",
                tooltip="Local staticfiles URL",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="resolved_latitude",
                output_type="float",
                tooltip="Resolved latitude used for capture",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="resolved_longitude",
                output_type="float",
                tooltip="Resolved longitude used for capture",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status",
                output_type="str",
                tooltip="Capture status",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

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

    @staticmethod
    def _save_image(raw: bytes, fmt: str) -> tuple[str, str]:
        file_name = f"streetview_clean_{int(time.time() * 1000)}.{fmt}"
        static_dir = Path(os.environ.get("GTN_STATICFILES_DIR", str(DEFAULT_STATICFILES_DIR)))
        static_dir.mkdir(parents=True, exist_ok=True)
        out_path = static_dir / file_name
        with out_path.open("wb") as f:
            f.write(raw)
        return str(out_path), f"/staticfiles/{file_name}"

    def _geocode_google(self, query: str, api_key: str) -> tuple[float | None, float | None]:
        try:
            response = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": query, "key": api_key},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results", []) if isinstance(payload, dict) else []
            if not results:
                return None, None
            location = results[0].get("geometry", {}).get("location", {})
            return _to_float(location.get("lat")), _to_float(location.get("lng"))
        except Exception:
            return None, None

    def process(self) -> None:
        query = str(self.parameter_values.get("search_query", "") or "").strip()
        lat = _to_float(self.parameter_values.get("latitude", 0.0))
        lng = _to_float(self.parameter_values.get("longitude", 0.0))
        api_key = self._resolve_google_api_key()

        self.parameter_output_values["captured_image"] = None
        self.parameter_output_values["captured_image_path"] = ""
        self.parameter_output_values["captured_image_url"] = ""

        if not api_key:
            self.parameter_output_values["resolved_latitude"] = lat
            self.parameter_output_values["resolved_longitude"] = lng
            self.parameter_output_values["status"] = (
                "Missing GOOGLE_MAPS_API_KEY (or api_key input). This clean node requires Street View Static API access."
            )
            return

        if query:
            parsed = _parse_latlng(query)
            if parsed:
                lat, lng = parsed
            else:
                glat, glng = self._geocode_google(query, api_key)
                if glat is not None and glng is not None:
                    lat, lng = glat, glng

        self.parameter_output_values["resolved_latitude"] = lat
        self.parameter_output_values["resolved_longitude"] = lng

        url = (
            "https://maps.googleapis.com/maps/api/streetview"
            f"?size=1280x720&location={quote_plus(f'{lat:.6f},{lng:.6f}')}"
            "&heading=0&pitch=0&fov=80"
            f"&key={quote_plus(api_key)}"
        )

        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            raw = resp.content
            if not raw:
                raise RuntimeError("Street View returned empty body.")

            img = Image.open(io.BytesIO(raw))
            width_px, height_px = img.size
            fmt = (img.format or "PNG").lower()
            if fmt == "jpg":
                fmt = "jpeg"
            if fmt not in {"png", "jpeg", "webp"}:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                raw = buf.getvalue()
                fmt = "png"

            path, static_url = self._save_image(raw, fmt)
            self.parameter_output_values["captured_image"] = ImageUrlArtifact(value=path, name="streetview_clean_capture")
            self.parameter_output_values["captured_image_path"] = path
            self.parameter_output_values["captured_image_url"] = static_url
            self.parameter_output_values["status"] = f"Street View capture saved: {path} ({width_px}x{height_px})"
        except Exception as exc:
            err_text = str(exc)
            auth_hint = (
                " Use a SERVER key and enable Street View Static API + billing."
                if "403" in err_text or "forbidden" in err_text.lower() or "not authorized" in err_text.lower()
                else ""
            )
            self.parameter_output_values["status"] = f"Street View capture failed: {exc}.{auth_hint}"

