"""Street View Capture node - strict Google Street View static snapshot output."""

from __future__ import annotations

import io
import os
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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class StreetViewCaptureNode(DataNode):
    """Capture Street View image as ImageArtifact (no map fallback)."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "GeoExplorer",
            "description": "Capture a Street View static image by lat/lng using Google API",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="latitude",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Street View latitude",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="api_key",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Google API key for server-side Street View Static requests (overrides secret if set).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="longitude",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Street View longitude",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="heading",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Street View camera heading (0-360)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="pitch",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Street View camera pitch (-90 to 90)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="fov",
                input_types=["float"],
                type="float",
                default_value=80.0,
                tooltip="Street View field of view",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                default_value=1280,
                tooltip="Capture width",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                default_value=720,
                tooltip="Capture height",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="streetview_image",
                output_type="ImageArtifact",
                tooltip="Street View capture as ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )
        self.add_parameter(
            Parameter(
                name="streetview_image_url_artifact",
                output_type="ImageUrlArtifact",
                tooltip="Street View URL artifact",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="streetview_image_url",
                output_type="str",
                tooltip="Street View URL",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="captured_image_path",
                output_type="str",
                tooltip="Saved local capture path",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="captured_image_url",
                output_type="str",
                tooltip="Saved local static URL path",
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
    def _build_streetview_url(
        lat: float,
        lng: float,
        api_key: str,
        width: int,
        height: int,
        heading: float,
        pitch: float,
        fov: float,
    ) -> str:
        return (
            "https://maps.googleapis.com/maps/api/streetview"
            f"?size={max(64, int(width))}x{max(64, int(height))}"
            f"&location={quote_plus(f'{lat:.6f},{lng:.6f}')}"
            f"&heading={heading:.1f}&pitch={pitch:.1f}&fov={fov:.1f}"
            f"&key={quote_plus(api_key)}"
        )

    @staticmethod
    def _save_image(raw: bytes, fmt: str) -> tuple[str, str]:
        file_name = f"streetview_capture_{int(time.time() * 1000)}.{fmt}"
        static_dir = Path(os.environ.get("GTN_STATICFILES_DIR", str(DEFAULT_STATICFILES_DIR)))
        static_dir.mkdir(parents=True, exist_ok=True)
        out_path = static_dir / file_name
        with out_path.open("wb") as f:
            f.write(raw)
        return str(out_path), f"/staticfiles/{file_name}"

    def process(self) -> None:
        lat = _to_float(self.parameter_values.get("latitude", 0.0))
        lng = _to_float(self.parameter_values.get("longitude", 0.0))
        heading = _to_float(self.parameter_values.get("heading", 0.0))
        pitch = _to_float(self.parameter_values.get("pitch", 0.0))
        fov = _to_float(self.parameter_values.get("fov", 80.0))
        width = int(_to_float(self.parameter_values.get("width", 1280), 1280))
        height = int(_to_float(self.parameter_values.get("height", 720), 720))
        api_key = self._resolve_google_api_key()

        if not api_key:
            self.parameter_output_values["status"] = (
                "Missing GOOGLE_MAPS_API_KEY. StreetViewCapture requires Google Street View Static API key."
            )
            self.parameter_output_values["streetview_image"] = None
            self.parameter_output_values["streetview_image_url_artifact"] = None
            self.parameter_output_values["streetview_image_url"] = ""
            self.parameter_output_values["captured_image_path"] = ""
            self.parameter_output_values["captured_image_url"] = ""
            return

        url = self._build_streetview_url(
            lat=lat,
            lng=lng,
            api_key=api_key,
            width=width,
            height=height,
            heading=heading,
            pitch=pitch,
            fov=fov,
        )
        self.parameter_output_values["streetview_image_url"] = url
        self.parameter_output_values["streetview_image_url_artifact"] = ImageUrlArtifact(
            value=url, name="streetview_capture"
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

            artifact = ImageArtifact(value=raw, width=width_px, height=height_px, format=fmt, name="streetview_capture")
            path, static_url = self._save_image(raw, fmt)
            self.parameter_output_values["streetview_image"] = artifact
            self.parameter_output_values["captured_image_path"] = path
            self.parameter_output_values["captured_image_url"] = static_url
            self.parameter_output_values["status"] = f"Street View capture saved: {path}"
        except Exception as exc:
            err_text = str(exc)
            auth_hint = (
                " Use a SERVER key (IP/None restriction), and enable Street View Static API + billing."
                if "403" in err_text or "forbidden" in err_text.lower() or "not authorized" in err_text.lower()
                else ""
            )
            self.parameter_output_values["streetview_image"] = None
            self.parameter_output_values["captured_image_path"] = ""
            self.parameter_output_values["captured_image_url"] = ""
            self.parameter_output_values["status"] = (
                f"Street View capture failed: {exc}.{auth_hint}"
            )
