"""Geo Explorer node - place search + lat/lng + Earth/Map/Street View URLs."""

from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image, ImageDraw

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.widget import Widget

logger = logging.getLogger(__name__)

GOOGLE_API_KEY_SECRET = "GOOGLE_MAPS_API_KEY"
DEFAULT_STATICFILES_DIR = Path(r"C:\Users\AI PC\GriptapeNodes\staticfiles")
LATLNG_PATTERN = re.compile(
    r"^\s*([+-]?\d{1,2}(?:\.\d+)?)\s*,\s*([+-]?\d{1,3}(?:\.\d+)?)\s*$"
)


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
    return (lat, lng)


def _build_snapshot_url(
    mode: str,
    lat: float,
    lng: float,
    api_key: str,
    zoom: int = 15,
) -> str:
    """Build a direct image URL for downstream image nodes."""
    if api_key:
        if mode == "street_view":
            return (
                "https://maps.googleapis.com/maps/api/streetview"
                f"?size=1280x720&location={quote_plus(f'{lat:.6f},{lng:.6f}')}"
                "&heading=0&pitch=0&fov=80"
                f"&key={quote_plus(api_key)}"
            )

        maptype = "satellite" if mode == "earth" else "roadmap"
        return (
            "https://maps.googleapis.com/maps/api/staticmap"
            f"?size=1280x720&center={quote_plus(f'{lat:.6f},{lng:.6f}')}"
            f"&zoom={max(1, int(zoom))}&maptype={maptype}"
            f"&markers=color:red%7C{quote_plus(f'{lat:.6f},{lng:.6f}')}"
            f"&key={quote_plus(api_key)}"
        )

    # Keyless fallback image endpoint (OSM static map).
    return (
        "https://staticmap.openstreetmap.de/staticmap.php"
        f"?center={lat:.6f},{lng:.6f}&zoom={max(1, int(zoom))}&size=1280x720"
        f"&markers={lat:.6f},{lng:.6f},red-pushpin"
    )


def _download_image_artifact(image_url: str) -> tuple[ImageArtifact | None, str, str, str]:
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
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            raw = buffer.getvalue()
            fmt = "png"

        artifact, static_path, static_url = _build_artifact_and_save(raw, width, height, fmt)
        return artifact, static_path, static_url, ""
    except Exception as exc:
        return None, "", "", f"Snapshot download failed: {exc}"


def _build_artifact_and_save(raw: bytes, width: int, height: int, fmt: str) -> tuple[ImageArtifact, str, str]:
    file_name = f"geo_capture_{int(time.time() * 1000)}.{fmt}"
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


def _build_url_artifact(path: str, static_url: str) -> ImageUrlArtifact | None:
    # Strict: only return local captured file reference (path or staticfiles URL).
    # Do not fall back to remote API URLs for captured_image output.
    value = (path or "").strip() or (static_url or "").strip()
    if not value:
        return None
    return ImageUrlArtifact(value=value, name="geo_capture")


def _build_osm_tile_capture(lat: float, lng: float, zoom: int = 15, width: int = 1280, height: int = 720) -> tuple[ImageArtifact | None, str, str, str]:
    """Build a local map image from OSM tile server as a robust fallback."""
    try:
        lat = max(-85.0511, min(85.0511, lat))
        z = max(1, min(19, int(zoom)))
        n = 2**z
        tile_size = 256

        x_tile_f = (lng + 180.0) / 360.0 * n
        lat_rad = math.radians(lat)
        y_tile_f = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n

        center_x_px = x_tile_f * tile_size
        center_y_px = y_tile_f * tile_size

        left_px = center_x_px - (width / 2.0)
        top_px = center_y_px - (height / 2.0)
        right_px = center_x_px + (width / 2.0)
        bottom_px = center_y_px + (height / 2.0)

        min_tx = int(math.floor(left_px / tile_size))
        max_tx = int(math.floor((right_px - 1) / tile_size))
        min_ty = int(math.floor(top_px / tile_size))
        max_ty = int(math.floor((bottom_px - 1) / tile_size))

        stitch_w = (max_tx - min_tx + 1) * tile_size
        stitch_h = (max_ty - min_ty + 1) * tile_size
        stitch = Image.new("RGB", (stitch_w, stitch_h), (18, 18, 18))

        fetched_any = False
        request_headers = {
            # OSM policy expects identifying User-Agent.
            "User-Agent": "GTN-LatLong-Geo-Library/0.2 (local capture fallback)",
        }
        for tx in range(min_tx, max_tx + 1):
            for ty in range(min_ty, max_ty + 1):
                if ty < 0 or ty >= n:
                    continue
                wrapped_tx = tx % n
                url = f"https://tile.openstreetmap.org/{z}/{wrapped_tx}/{ty}.png"
                try:
                    resp = requests.get(url, timeout=10, headers=request_headers)
                    resp.raise_for_status()
                    if b"access blocked" in resp.content.lower():
                        continue
                    tile_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    ox = (tx - min_tx) * tile_size
                    oy = (ty - min_ty) * tile_size
                    stitch.paste(tile_img, (ox, oy))
                    fetched_any = True
                except Exception:
                    continue

        if not fetched_any:
            return None, "", "", "OSM tile fallback failed: no tiles fetched."

        crop_left = int(round(left_px - (min_tx * tile_size)))
        crop_top = int(round(top_px - (min_ty * tile_size)))
        crop_right = crop_left + width
        crop_bottom = crop_top + height
        final_img = stitch.crop((crop_left, crop_top, crop_right, crop_bottom))

        # Add a center marker so users know the target point.
        draw = ImageDraw.Draw(final_img)
        cx, cy = width // 2, height // 2
        r = 8
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(220, 30, 30), outline=(255, 255, 255), width=2)

        buffer = io.BytesIO()
        final_img.save(buffer, format="PNG")
        raw = buffer.getvalue()
        artifact, static_path, static_url = _build_artifact_and_save(raw, width, height, "png")
        return artifact, static_path, static_url, ""
    except Exception as exc:
        return None, "", "", f"OSM tile fallback failed: {exc}"


def _capture_url_via_playwright(url: str, width: int = 1280, height: int = 720) -> tuple[ImageArtifact | None, str, str, str]:
    """Capture URL pixels via headless Chromium screenshot (best-effort)."""
    if not url:
        return None, "", "", "Playwright capture failed: empty URL."
    try:
        # Import lazily so normal node runs are unaffected if playwright is missing.
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:
        return None, "", "", f"Playwright capture unavailable: {exc}"

    async def _capture_async() -> bytes:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": max(320, int(width)), "height": max(240, int(height))})
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1200)
            png = await page.screenshot(type="png", full_page=False)
            await context.close()
            await browser.close()
            return png

    def _run_capture_bytes() -> bytes:
        try:
            # If there is no running event loop in this thread, run directly.
            asyncio.get_running_loop()
            has_loop = True
        except RuntimeError:
            has_loop = False

        if not has_loop:
            return asyncio.run(_capture_async())

        # GTN may already run an asyncio loop. Run capture in a dedicated thread.
        result_q: queue.Queue[tuple[bytes | None, Exception | None]] = queue.Queue(maxsize=1)

        def _runner() -> None:
            try:
                result_q.put((asyncio.run(_capture_async()), None))
            except Exception as thread_exc:
                result_q.put((None, thread_exc))

        t = threading.Thread(target=_runner, name="gtn-playwright-capture", daemon=True)
        t.start()
        t.join(timeout=45)
        if t.is_alive():
            raise TimeoutError("Playwright capture timed out.")
        png_bytes, thread_error = result_q.get_nowait()
        if thread_error:
            raise thread_error
        return png_bytes or b""

    try:
        png_bytes = _run_capture_bytes()
        if not png_bytes:
            return None, "", "", "Playwright capture failed: empty screenshot bytes."
        img = Image.open(io.BytesIO(png_bytes))
        w, h = img.size
        artifact, static_path, static_url = _build_artifact_and_save(png_bytes, w, h, "png")
        return artifact, static_path, static_url, ""
    except Exception as exc:
        return None, "", "", f"Playwright capture failed: {exc}"


class GeoExplorerNode(DataNode):
    """Explore locations with a single node for map, earth, and street view."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "GeoExplorer",
            "description": "Search locations and generate Google Earth/Map/Street View URLs",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)
        self._last_capture_nonce = ""
        self._cached_capture_artifact: ImageArtifact | None = None
        self._cached_capture_path = ""
        self._cached_capture_url = ""

        self.add_parameter(
            Parameter(
                name="search_query",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Place, street, city, or 'lat,lng' (example: 40.6892,-74.0445)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="latitude",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Fallback latitude when no search query is provided",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="longitude",
                input_types=["float"],
                type="float",
                default_value=0.0,
                tooltip="Fallback longitude when no search query is provided",
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
                tooltip="Google API key for server-side geocode/snapshot calls (overrides secret if set).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="viewer",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={"url": "", "mode": "earth", "query": "", "capture_nonce": ""},
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
                tooltip="Optional capture trigger nonce from widget button",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        with ParameterGroup(name="Outputs", collapsed=True) as outputs_group:
            Parameter(
                name="resolved_latitude",
                output_type="float",
                tooltip="Resolved latitude",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="resolved_longitude",
                output_type="float",
                tooltip="Resolved longitude",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="formatted_address",
                output_type="str",
                tooltip="Formatted location result when available",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="earth_url",
                output_type="str",
                tooltip="Google Earth web URL",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="earth_3d_url",
                output_type="str",
                tooltip="True Google Earth 3D URL (open in browser tab)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
            Parameter(
                name="map_url",
                output_type="str",
                tooltip="Google Maps URL",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="street_view_url",
                output_type="str",
                tooltip="Google Street View URL",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="current_url",
                output_type="str",
                tooltip="Current URL for selected mode",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="status",
                output_type="str",
                tooltip="Resolution status",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="snapshot_image",
                output_type="ImageUrlArtifact",
                tooltip="Direct map/street snapshot image as ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
            Parameter(
                name="snapshot_image_url",
                output_type="str",
                tooltip="Direct map/street snapshot image URL",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
            Parameter(
                name="snapshot_image_artifact",
                output_type="ImageArtifact",
                tooltip="Downloaded snapshot image bytes as ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
            Parameter(
                name="captured_image",
                output_type="ImageUrlArtifact",
                tooltip="Captured image as URL/path artifact for direct connector usage",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
            Parameter(
                name="captured_image_url_artifact",
                output_type="ImageUrlArtifact",
                tooltip="Captured image URL/path artifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
            Parameter(
                name="captured_image_path",
                output_type="str",
                tooltip="Saved capture path in local staticfiles folder",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
            Parameter(
                name="captured_image_url",
                output_type="str",
                tooltip="Saved capture URL in local staticfiles folder",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        self.add_node_element(outputs_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "viewer" and isinstance(value, dict):
            mode = _clean_mode(value.get("mode", self.parameter_values.get("mode", "earth")))
            query = str(value.get("query", self.parameter_values.get("search_query", "")) or "").strip()
            if query:
                self.parameter_values["search_query"] = query
            self.parameter_values["mode"] = mode
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

        # GTN secret manager path (works when secret is registered in library settings).
        try:
            secret = GriptapeNodes.SecretsManager().get_secret(GOOGLE_API_KEY_SECRET)
            if isinstance(secret, str) and secret.strip():
                return secret.strip()
        except Exception:
            pass

        # Additional fallback for environments using config service lookup.
        try:
            config_value = self.get_config_value(service="Google Maps", value=GOOGLE_API_KEY_SECRET)
            if isinstance(config_value, str) and config_value.strip():
                return config_value.strip()
        except Exception:
            pass

        return ""

    def _geocode(self, query: str, api_key: str = "") -> tuple[float | None, float | None, str]:
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
                    location = first.get("geometry", {}).get("location", {})
                    lat = _to_float(location.get("lat"))
                    lng = _to_float(location.get("lng"))
                    address = str(first.get("formatted_address", query))
                    return lat, lng, address
            except Exception as exc:
                logger.warning("Google geocode failed for '%s': %s", query, exc)

        # OpenStreetMap fallback when API key is missing/unavailable.
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": "GTN-LatLong-Geo-Library/0.1"},
                timeout=12,
            )
            response.raise_for_status()
            results = response.json()
            if isinstance(results, list) and results:
                first = results[0]
                lat = _to_float(first.get("lat"))
                lng = _to_float(first.get("lon"))
                address = str(first.get("display_name", query))
                return lat, lng, address
        except Exception as exc:
            logger.warning("Fallback geocode failed for '%s': %s", query, exc)

        return None, None, ""

    @staticmethod
    def _build_urls(
        lat: float,
        lng: float,
        query: str,
        zoom: int,
        heading: float,
        pitch: float,
        api_key: str,
    ) -> dict[str, str]:
        has_query = bool((query or "").strip())
        query_value = query.strip() if has_query else f"{lat},{lng}"
        encoded_query = quote_plus(query_value)
        earth_3d_url = (
            f"https://earth.google.com/web/search/{encoded_query}"
            if has_query
            else f"https://earth.google.com/web/@{lat:.6f},{lng:.6f},1200a,1400d,35y,{heading:.2f}h,{pitch:.2f}t,0r"
        )

        map_url = f"https://maps.google.com/maps?q={encoded_query}&z={max(1, int(zoom))}&output=embed"
        earth_url = (
            f"https://earth.google.com/web/@{lat:.6f},{lng:.6f},1200a,1400d,35y,"
            f"{heading:.2f}h,{pitch:.2f}t,0r"
        )
        street_view_url = (
            "https://www.google.com/maps/@?api=1&map_action=pano"
            f"&viewpoint={quote_plus(f'{lat:.6f},{lng:.6f}')}"
            f"&heading={heading:.1f}&pitch={pitch:.1f}&fov=80"
        )

        # Use iframe-safe embed endpoints when an API key is available.
        if api_key:
            center_value = quote_plus(f"{lat:.6f},{lng:.6f}")
            map_url = (
                "https://www.google.com/maps/embed/v1/place"
                f"?key={quote_plus(api_key)}&q={encoded_query}&zoom={max(1, int(zoom))}"
            )
            # Earth web itself is not iframe-safe. Use satellite embed as the Earth-like mode.
            earth_url = (
                "https://www.google.com/maps/embed/v1/view"
                f"?key={quote_plus(api_key)}&center={center_value}&zoom={max(1, int(zoom))}"
                "&maptype=satellite"
            )
            street_view_url = (
                "https://www.google.com/maps/embed/v1/streetview"
                f"?key={quote_plus(api_key)}&location={center_value}"
                f"&heading={heading:.1f}&pitch={pitch:.1f}&fov=80"
            )

        # For text-only inputs, keep map URL query-oriented while still exposing coordinate URLs.
        if has_query and not api_key:
            earth_url = earth_3d_url
            street_view_url = (
                "https://www.google.com/maps/@?api=1&map_action=pano"
                f"&viewpoint={encoded_query}&heading={heading:.1f}&pitch={pitch:.1f}&fov=80"
            )

        return {
            "map_url": map_url,
            "earth_url": earth_url,
            "earth_3d_url": earth_3d_url,
            "street_view_url": street_view_url,
        }

    def process(self) -> None:
        mode = _clean_mode(self.parameter_values.get("mode", "earth"))
        query = str(self.parameter_values.get("search_query", "") or "").strip()
        lat = _to_float(self.parameter_values.get("latitude", 0.0))
        lng = _to_float(self.parameter_values.get("longitude", 0.0))
        zoom = 15
        heading = 0.0
        pitch = 0.0
        api_key = self._resolve_google_api_key()

        formatted_address = ""
        status = ""

        if query:
            parsed_latlng = _parse_latlng(query)
            if parsed_latlng:
                lat, lng = parsed_latlng
                formatted_address = f"{lat:.6f}, {lng:.6f}"
                status = "Resolved from lat,lng input."
            else:
                resolved_lat, resolved_lng, resolved_address = self._geocode(query, api_key=api_key)
                if resolved_lat is not None and resolved_lng is not None:
                    lat = resolved_lat
                    lng = resolved_lng
                    formatted_address = resolved_address or query
                    status = "Resolved from place/street search."
                else:
                    formatted_address = query
                    status = (
                        "Could not geocode search text. Using fallback coordinates from latitude/longitude inputs."
                    )
        else:
            formatted_address = f"{lat:.6f}, {lng:.6f}"
            status = "Using latitude/longitude inputs."

        urls = self._build_urls(
            lat=lat,
            lng=lng,
            query=query,
            zoom=zoom,
            heading=heading,
            pitch=pitch,
            api_key=api_key,
        )
        capture_nonce = str(self.parameter_values.get("capture_nonce", "") or "")
        should_capture = bool(capture_nonce and capture_nonce != self._last_capture_nonce)

        current_url = urls["earth_url"]
        if mode == "map":
            current_url = urls["map_url"]
        elif mode == "street_view":
            current_url = urls["street_view_url"]

        viewer_payload = {
            "url": current_url,
            "mode": mode,
            "query": query or f"{lat:.6f},{lng:.6f}",
            "capture_nonce": capture_nonce,
            "latitude": lat,
            "longitude": lng,
            "zoom": zoom,
            "heading": heading,
            "pitch": pitch,
            "earth_url": urls["earth_url"],
            "earth_3d_url": urls["earth_3d_url"],
            "map_url": urls["map_url"],
            "street_view_url": urls["street_view_url"],
        }
        snapshot_image_url = _build_snapshot_url(
            mode=mode,
            lat=lat,
            lng=lng,
            api_key=api_key,
            zoom=zoom,
        )
        snapshot_image = ImageUrlArtifact(value=snapshot_image_url, name="geo_snapshot")
        snapshot_image_artifact = None
        captured_image_path = self._cached_capture_path
        captured_image_url = self._cached_capture_url
        captured_image_url_artifact = _build_url_artifact(
            path=captured_image_path,
            static_url=captured_image_url,
        )
        snapshot_error = ""
        if should_capture:
            # First attempt: pixel capture of the current visible URL (iframe-like behavior).
            # This avoids Street View Static API auth limitations when embed URL already works.
            snapshot_image_artifact, captured_image_path, captured_image_url, snapshot_error = _capture_url_via_playwright(
                current_url, width=1280, height=720
            )
            playwright_error = snapshot_error
            if snapshot_image_artifact is None and mode != "street_view":
                snapshot_image_artifact, captured_image_path, captured_image_url, snapshot_error = _download_image_artifact(snapshot_image_url)
                if snapshot_error and playwright_error:
                    snapshot_error = f"{playwright_error} {snapshot_error}"
            elif snapshot_image_artifact is None and mode == "street_view":
                # Keep Street View strictness (no map fallback), but allow direct Street View
                # static image download when browser capture is unavailable in runtime.
                snapshot_image_artifact, captured_image_path, captured_image_url, static_error = _download_image_artifact(snapshot_image_url)
                if snapshot_image_artifact is not None:
                    snapshot_error = (
                        f"{playwright_error} Street View static fallback applied."
                        if playwright_error
                        else "Street View static fallback applied."
                    )
                else:
                    snapshot_error = f"{playwright_error} {static_error}".strip()
            if snapshot_image_artifact is None:
                if mode == "street_view":
                    # For street_view capture, stay strict: capture what is rendered in-node,
                    # and do not switch to map/tile fallbacks.
                    captured_image_path = ""
                    captured_image_url = ""
                    snapshot_image = ImageUrlArtifact(value=snapshot_image_url, name="geo_snapshot_street_failed")
                    if snapshot_error:
                        snapshot_error = f"{snapshot_error} Street View capture failed."
                    else:
                        snapshot_error = "Street View node-display capture failed."
                else:
                    # Non-street modes can still use map/tile fallbacks.
                    fallback_url = _build_snapshot_url(
                        mode="map",
                        lat=lat,
                        lng=lng,
                        api_key="",
                        zoom=zoom,
                    )
                    fallback_artifact, fallback_path, fallback_static_url, fallback_error = _download_image_artifact(fallback_url)
                    if fallback_artifact is not None:
                        snapshot_image_url = fallback_url
                        snapshot_image = ImageUrlArtifact(value=snapshot_image_url, name="geo_snapshot_fallback")
                        snapshot_image_artifact = fallback_artifact
                        captured_image_path = fallback_path
                        captured_image_url = fallback_static_url
                        snapshot_error = (
                            f"{snapshot_error} Map snapshot fallback applied."
                            if snapshot_error
                            else "Map snapshot fallback applied."
                        )
                    else:
                        # Second-level fallback: compose image directly from OSM tiles.
                        osm_artifact, osm_path, osm_url, osm_error = _build_osm_tile_capture(
                            lat=lat,
                            lng=lng,
                            zoom=zoom,
                            width=640,
                            height=360,
                        )
                        if osm_artifact is not None:
                            snapshot_image_url = fallback_url
                            snapshot_image = ImageUrlArtifact(value=snapshot_image_url, name="geo_snapshot_osm_tiles")
                            snapshot_image_artifact = osm_artifact
                            captured_image_path = osm_path
                            captured_image_url = osm_url
                            snapshot_error = (
                                f"{snapshot_error} OSM tile fallback applied."
                                if snapshot_error
                                else "OSM tile fallback applied."
                            )
                        else:
                            snapshot_error = f"{snapshot_error} {fallback_error} {osm_error}".strip()

            if snapshot_image_artifact is not None:
                self._cached_capture_artifact = snapshot_image_artifact
                self._cached_capture_path = captured_image_path
                self._cached_capture_url = captured_image_url
                self._last_capture_nonce = capture_nonce
            if mode == "street_view" and snapshot_image_artifact is None:
                captured_image_url_artifact = None
            else:
                captured_image_url_artifact = _build_url_artifact(
                    path=captured_image_path,
                    static_url=captured_image_url,
                )

        self.parameter_output_values["resolved_latitude"] = lat
        self.parameter_output_values["resolved_longitude"] = lng
        self.parameter_output_values["formatted_address"] = formatted_address
        self.parameter_output_values["earth_url"] = urls["earth_url"]
        self.parameter_output_values["earth_3d_url"] = urls["earth_3d_url"]
        self.parameter_output_values["map_url"] = urls["map_url"]
        self.parameter_output_values["street_view_url"] = urls["street_view_url"]
        self.parameter_output_values["current_url"] = current_url
        self.parameter_output_values["snapshot_image"] = snapshot_image
        self.parameter_output_values["snapshot_image_url"] = snapshot_image_url
        self.parameter_output_values["snapshot_image_artifact"] = snapshot_image_artifact
        self.parameter_output_values["captured_image"] = captured_image_url_artifact
        self.parameter_output_values["captured_image_url_artifact"] = captured_image_url_artifact
        self.parameter_output_values["captured_image_path"] = captured_image_path
        self.parameter_output_values["captured_image_url"] = captured_image_url
        if api_key:
            status = f"{status} Google API key detected (Embed + Geocoding active)."
        else:
            status = (
                f"{status} No Google API key detected; Earth/Street may fail to embed in iframe."
            )
        if snapshot_error:
            status = f"{status} {snapshot_error}"
        elif captured_image_path:
            status = f"{status} Capture saved: {captured_image_path}"
        elif not should_capture:
            status = f"{status} Capture idle (click Capture button)."

        self.parameter_output_values["status"] = status
        self.parameter_output_values["viewer"] = viewer_payload
        self.parameter_values["viewer"] = viewer_payload
