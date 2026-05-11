from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget


class HawkAnamorphicNode(DataNode):
    """Apply a Hawk-inspired anamorphic look to an image file."""

    _LENS_PROFILES: dict[str, dict[str, float]] = {
        "28": {"ca": 1.35, "edge_blur": 1.30, "vignette": 1.10, "breathing": 0.055},
        "35": {"ca": 1.10, "edge_blur": 1.10, "vignette": 1.00, "breathing": 0.050},
        "45": {"ca": 0.95, "edge_blur": 0.95, "vignette": 0.90, "breathing": 0.045},
        "55": {"ca": 0.80, "edge_blur": 0.82, "vignette": 0.82, "breathing": 0.040},
        "65": {"ca": 0.72, "edge_blur": 0.74, "vignette": 0.78, "breathing": 0.036},
        "80": {"ca": 0.64, "edge_blur": 0.65, "vignette": 0.72, "breathing": 0.032},
        "110": {"ca": 0.55, "edge_blur": 0.56, "vignette": 0.62, "breathing": 0.026},
    }

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "Anamorphic",
            "description": "Apply a Hawk-style anamorphic post look from lens profile + focus.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="input_image_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Input image file path.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_image_path",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional output path. If empty, writes next to input as *_hawk.ext.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="lens_mm",
                input_types=["str"],
                type="str",
                default_value="45",
                tooltip="Lens profile: 28, 35, 45, 55, 65, 80, or 110.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="focus_m",
                input_types=["float"],
                type="float",
                default_value=12.0,
                tooltip="Focus distance in meters. Closer focus increases breathing.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="chromatic_aberration",
                input_types=["float"],
                type="float",
                default_value=0.70,
                tooltip="Chromatic shift intensity (0.0-2.0).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="edge_softness",
                input_types=["float"],
                type="float",
                default_value=0.65,
                tooltip="Edge blur and softness falloff (0.0-2.0).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="vignette",
                input_types=["float"],
                type="float",
                default_value=0.45,
                tooltip="Vignette amount (0.0-2.0).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="breathing_strength",
                input_types=["float"],
                type="float",
                default_value=1.0,
                tooltip="Focus breathing strength multiplier (0.0-2.0).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="hawk_widget",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={
                    "inputImagePath": "",
                    "outputImagePath": "",
                    "method": "distort",
                    "lensMm": "45",
                    "focusM": 12.0,
                    "useGpuIfAvailable": False,
                    "chromaticAberration": 0.70,
                    "disableChromaticAberration": False,
                    "edgeSoftness": 0.65,
                    "disableEdgeSoftness": False,
                    "maskScaleW": 1.0,
                    "maskScaleH": 1.0,
                    "vignette": 0.45,
                    "disableVignette": False,
                    "breathingStrength": 1.0,
                    "disableAll": False,
                    "statusMessage": "Ready.",
                    "profileUsed": {},
                },
                tooltip="Interactive Hawk anamorphic control panel.",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="HawkAnamorphicWidget", library="Hawk Anamorphic Library")},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_image_path_out",
                output_type="str",
                tooltip="Processed image output path.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status_message",
                output_type="str",
                tooltip="Process result status.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="profile_used",
                output_type="dict",
                tooltip="Resolved lens profile values.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _resolve_profile(self, lens_mm: str) -> tuple[str, dict[str, float]]:
        cleaned = str(lens_mm).strip().replace("mm", "")
        if cleaned in self._LENS_PROFILES:
            return cleaned, self._LENS_PROFILES[cleaned]

        # Fallback to nearest known focal length.
        known = sorted(int(k) for k in self._LENS_PROFILES.keys())
        try:
            requested = int(float(cleaned))
            nearest = min(known, key=lambda x: abs(x - requested))
            key = str(nearest)
            return key, self._LENS_PROFILES[key]
        except Exception:
            return "45", self._LENS_PROFILES["45"]

    @staticmethod
    def _default_output_path(input_path: Path) -> Path:
        return input_path.with_name(f"{input_path.stem}_hawk{input_path.suffix}")

    @staticmethod
    def _zoom_center(rgb: np.ndarray, factor: float) -> np.ndarray:
        if factor <= 1.0001:
            return rgb

        h, w = rgb.shape[:2]
        image = Image.fromarray((np.clip(rgb, 0.0, 1.0) * 255).astype(np.uint8), mode="RGB")
        resized = image.resize((max(1, int(round(w * factor))), max(1, int(round(h * factor)))), Image.BICUBIC)
        rw, rh = resized.size
        left = max(0, (rw - w) // 2)
        top = max(0, (rh - h) // 2)
        cropped = resized.crop((left, top, left + w, top + h))
        return np.asarray(cropped).astype(np.float32) / 255.0

    @staticmethod
    def _shift_channel(channel: np.ndarray, dx: int) -> np.ndarray:
        if dx == 0:
            return channel
        shifted = np.roll(channel, shift=dx, axis=1)
        if dx > 0:
            shifted[:, :dx] = channel[:, :1]
        else:
            shifted[:, dx:] = channel[:, -1:]
        return shifted

    @staticmethod
    def _edge_mask(height: int, width: int) -> np.ndarray:
        yy, xx = np.mgrid[0:height, 0:width]
        nx = (xx - (width / 2.0)) / max(1.0, width / 2.0)
        ny = (yy - (height / 2.0)) / max(1.0, height / 2.0)
        rr = np.sqrt(nx * nx + ny * ny)
        mask = np.clip((rr - 0.34) / 0.66, 0.0, 1.0)
        return mask.astype(np.float32)

    @staticmethod
    def _extract_widget_state(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def process(self) -> None:
        widget_state = self._extract_widget_state(self.parameter_values.get("hawk_widget", {}))

        input_path_text = str(self.parameter_values.get("input_image_path", "")).strip()
        if not input_path_text:
            input_path_text = str(widget_state.get("inputImagePath", "")).strip()

        output_path_text = str(self.parameter_values.get("output_image_path", "")).strip()
        if not output_path_text:
            output_path_text = str(widget_state.get("outputImagePath", "")).strip()

        lens_mm = str(self.parameter_values.get("lens_mm", "45")).strip()
        if lens_mm == "45" and str(widget_state.get("lensMm", "")).strip():
            lens_mm = str(widget_state.get("lensMm", "45")).strip()

        focus_m = float(self.parameter_values.get("focus_m", 12.0))
        if focus_m == 12.0 and widget_state.get("focusM") is not None:
            focus_m = float(widget_state.get("focusM", 12.0))

        chromatic = float(self.parameter_values.get("chromatic_aberration", 0.70))
        if chromatic == 0.70 and widget_state.get("chromaticAberration") is not None:
            chromatic = float(widget_state.get("chromaticAberration", 0.70))

        edge_softness = float(self.parameter_values.get("edge_softness", 0.65))
        if edge_softness == 0.65 and widget_state.get("edgeSoftness") is not None:
            edge_softness = float(widget_state.get("edgeSoftness", 0.65))

        vignette = float(self.parameter_values.get("vignette", 0.45))
        if vignette == 0.45 and widget_state.get("vignette") is not None:
            vignette = float(widget_state.get("vignette", 0.45))

        breathing_strength = float(self.parameter_values.get("breathing_strength", 1.0))
        if breathing_strength == 1.0 and widget_state.get("breathingStrength") is not None:
            breathing_strength = float(widget_state.get("breathingStrength", 1.0))
        method = str(widget_state.get("method", "distort")).strip().lower()
        if method not in {"distort", "undistort", "off"}:
            method = "distort"
        disable_all = bool(widget_state.get("disableAll", False))
        disable_chromatic = bool(widget_state.get("disableChromaticAberration", False))
        disable_edge = bool(widget_state.get("disableEdgeSoftness", False))
        disable_vignette = bool(widget_state.get("disableVignette", False))
        mask_scale_w = float(widget_state.get("maskScaleW", 1.0) or 1.0)
        mask_scale_h = float(widget_state.get("maskScaleH", 1.0) or 1.0)
        use_gpu_if_available = bool(widget_state.get("useGpuIfAvailable", False))

        if not input_path_text:
            self.parameter_output_values["status_message"] = "Input path is required."
            self.parameter_output_values["output_image_path_out"] = ""
            self.parameter_output_values["profile_used"] = {}
            self.parameter_output_values["hawk_widget"] = {
                "inputImagePath": "",
                "outputImagePath": output_path_text,
                "method": method,
                "lensMm": lens_mm,
                "focusM": focus_m,
                "useGpuIfAvailable": use_gpu_if_available,
                "chromaticAberration": chromatic,
                "disableChromaticAberration": disable_chromatic,
                "edgeSoftness": edge_softness,
                "disableEdgeSoftness": disable_edge,
                "maskScaleW": mask_scale_w,
                "maskScaleH": mask_scale_h,
                "vignette": vignette,
                "disableVignette": disable_vignette,
                "breathingStrength": breathing_strength,
                "disableAll": disable_all,
                "statusMessage": "Input path is required.",
                "profileUsed": {},
            }
            return

        input_path = Path(input_path_text)
        if not input_path.exists():
            self.parameter_output_values["status_message"] = f"Input file not found: {input_path}"
            self.parameter_output_values["output_image_path_out"] = ""
            self.parameter_output_values["profile_used"] = {}
            self.parameter_output_values["hawk_widget"] = {
                "inputImagePath": input_path_text,
                "outputImagePath": output_path_text,
                "method": method,
                "lensMm": lens_mm,
                "focusM": focus_m,
                "useGpuIfAvailable": use_gpu_if_available,
                "chromaticAberration": chromatic,
                "disableChromaticAberration": disable_chromatic,
                "edgeSoftness": edge_softness,
                "disableEdgeSoftness": disable_edge,
                "maskScaleW": mask_scale_w,
                "maskScaleH": mask_scale_h,
                "vignette": vignette,
                "disableVignette": disable_vignette,
                "breathingStrength": breathing_strength,
                "disableAll": disable_all,
                "statusMessage": f"Input file not found: {input_path}",
                "profileUsed": {},
            }
            return

        profile_key, profile = self._resolve_profile(lens_mm)
        chromatic = self._clamp(chromatic, 0.0, 2.0)
        edge_softness = self._clamp(edge_softness, 0.0, 2.0)
        vignette = self._clamp(vignette, 0.0, 2.0)
        breathing_strength = self._clamp(breathing_strength, 0.0, 2.0)
        focus_m = self._clamp(focus_m, 1.0, 100.0)

        output_path = Path(output_path_text) if output_path_text else self._default_output_path(input_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            source = Image.open(input_path)
            has_alpha = source.mode in {"RGBA", "LA"} or "transparency" in source.info
            rgba = source.convert("RGBA")
            arr = np.asarray(rgba).astype(np.float32) / 255.0

            rgb = arr[:, :, :3]
            alpha = arr[:, :, 3:4] if has_alpha else None

            if disable_all or method == "off":
                if alpha is not None:
                    out_image = Image.fromarray((np.clip(arr, 0.0, 1.0) * 255).astype(np.uint8), mode="RGBA")
                else:
                    out_image = Image.fromarray((np.clip(rgb, 0.0, 1.0) * 255).astype(np.uint8), mode="RGB")
                out_image.save(output_path)
                profile_used = {
                    "lens_mm": profile_key,
                    "method": "off" if method == "off" else method,
                    "bypassed": True,
                }
                status_message = f"Hawk look bypassed ({'Turn Off' if method == 'off' else 'Disable All'})."
                self.parameter_output_values["output_image_path_out"] = str(output_path)
                self.parameter_output_values["status_message"] = status_message
                self.parameter_output_values["profile_used"] = profile_used
                self.parameter_output_values["hawk_widget"] = {
                    "inputImagePath": input_path_text,
                    "outputImagePath": str(output_path),
                    "method": method,
                    "lensMm": profile_key,
                    "focusM": focus_m,
                    "useGpuIfAvailable": use_gpu_if_available,
                    "chromaticAberration": chromatic,
                    "disableChromaticAberration": disable_chromatic,
                    "edgeSoftness": edge_softness,
                    "disableEdgeSoftness": disable_edge,
                    "maskScaleW": mask_scale_w,
                    "maskScaleH": mask_scale_h,
                    "vignette": vignette,
                    "disableVignette": disable_vignette,
                    "breathingStrength": breathing_strength,
                    "disableAll": disable_all,
                    "statusMessage": status_message,
                    "profileUsed": profile_used,
                }
                return

            # Closer focus values increase breathing, matching the practical use case.
            focus_factor = (100.0 - focus_m) / 99.0
            zoom = 1.0 + (focus_factor * profile["breathing"] * breathing_strength)
            if method == "undistort":
                zoom = 1.0 / max(0.5, zoom)
            rgb = self._zoom_center(rgb, zoom)

            h, w = rgb.shape[:2]
            edge_mask = self._edge_mask(h, w)
            edge_mask = np.power(
                np.clip(edge_mask * self._clamp((mask_scale_w + mask_scale_h) * 0.5, 0.25, 4.0), 0.0, 1.0),
                1.0,
            )

            shift_px = int(round((0.75 + profile["ca"]) * chromatic * 1.8))
            if method == "undistort":
                shift_px = -shift_px
            if not disable_chromatic:
                red = self._shift_channel(rgb[:, :, 0], shift_px)
                green = rgb[:, :, 1]
                blue = self._shift_channel(rgb[:, :, 2], -shift_px)
                rgb = np.stack([red, green, blue], axis=2)

            blur_radius = edge_softness * (0.8 + profile["edge_blur"] * 1.7)
            if not disable_edge and blur_radius > 0.01:
                blur_img = Image.fromarray((np.clip(rgb, 0.0, 1.0) * 255).astype(np.uint8), mode="RGB")
                blur_img = blur_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                blur_arr = np.asarray(blur_img).astype(np.float32) / 255.0
                blend = np.power(edge_mask, 1.2)[:, :, None]
                rgb = rgb * (1.0 - blend) + blur_arr * blend

            vignette_amount = vignette * (0.35 + 0.65 * profile["vignette"])
            if not disable_vignette:
                if method == "undistort":
                    brighten = 1.0 + np.power(edge_mask, 1.25) * vignette_amount * 0.45
                    rgb = np.clip(rgb * brighten[:, :, None], 0.0, 1.0)
                else:
                    darken = 1.0 - np.power(edge_mask, 1.25) * vignette_amount
                    rgb = np.clip(rgb * darken[:, :, None], 0.0, 1.0)

            if alpha is not None:
                out = np.concatenate([rgb, alpha], axis=2)
                out_image = Image.fromarray((np.clip(out, 0.0, 1.0) * 255).astype(np.uint8), mode="RGBA")
            else:
                out_image = Image.fromarray((np.clip(rgb, 0.0, 1.0) * 255).astype(np.uint8), mode="RGB")

            out_image.save(output_path)

            profile_used = {
                "lens_mm": profile_key,
                "method": method,
                "focus_m": focus_m,
                "zoom_factor": zoom,
                "chromatic_shift_px": shift_px,
                "blur_radius": blur_radius,
                "vignette_amount": vignette_amount,
                "disable_chromatic_aberration": disable_chromatic,
                "disable_edge_softness": disable_edge,
                "disable_vignette": disable_vignette,
                "disable_all": disable_all,
            }
            status_message = f"Applied Hawk {method} look ({profile_key}mm) to {input_path.name}."
            self.parameter_output_values["output_image_path_out"] = str(output_path)
            self.parameter_output_values["status_message"] = status_message
            self.parameter_output_values["profile_used"] = profile_used
            self.parameter_output_values["hawk_widget"] = {
                "inputImagePath": input_path_text,
                "outputImagePath": str(output_path),
                "method": method,
                "lensMm": profile_key,
                "focusM": focus_m,
                "useGpuIfAvailable": use_gpu_if_available,
                "chromaticAberration": chromatic,
                "disableChromaticAberration": disable_chromatic,
                "edgeSoftness": edge_softness,
                "disableEdgeSoftness": disable_edge,
                "maskScaleW": mask_scale_w,
                "maskScaleH": mask_scale_h,
                "vignette": vignette,
                "disableVignette": disable_vignette,
                "breathingStrength": breathing_strength,
                "disableAll": disable_all,
                "statusMessage": status_message,
                "profileUsed": profile_used,
            }
        except Exception as exc:
            status_message = f"Processing failed: {exc}"
            self.parameter_output_values["output_image_path_out"] = ""
            self.parameter_output_values["status_message"] = status_message
            profile_used = {
                "lens_mm": profile_key,
            }
            self.parameter_output_values["profile_used"] = profile_used
            self.parameter_output_values["hawk_widget"] = {
                "inputImagePath": input_path_text,
                "outputImagePath": output_path_text,
                "method": method,
                "lensMm": profile_key,
                "focusM": focus_m,
                "useGpuIfAvailable": use_gpu_if_available,
                "chromaticAberration": chromatic,
                "disableChromaticAberration": disable_chromatic,
                "edgeSoftness": edge_softness,
                "disableEdgeSoftness": disable_edge,
                "maskScaleW": mask_scale_w,
                "maskScaleH": mask_scale_h,
                "vignette": vignette,
                "disableVignette": disable_vignette,
                "breathingStrength": breathing_strength,
                "disableAll": disable_all,
                "statusMessage": status_message,
                "profileUsed": profile_used,
            }
