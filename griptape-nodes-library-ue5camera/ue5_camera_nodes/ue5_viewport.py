"""UE5 Viewport node - live UE5 view via Pixel Streaming with screenshot capture."""

import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget

logger = logging.getLogger(__name__)


class UE5Viewport(DataNode):
    """Live UE5 viewport via Pixel Streaming with screenshot capture.

    Shows the UE5 editor viewport directly inside this node.
    Click the button to Load the stream, then click again to Capture a screenshot.

    Setup:
        1. In UE5: enable Pixel Streaming plugin, restart
        2. Toolbar > Pixel Streaming > Stream Level Editor
        3. Click Load (default URL: http://127.0.0.1)
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "UE5Camera",
            "description": "Live UE5 viewport with screenshot capture",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="stream_url",
                input_types=["str"],
                type="str",
                default_value="http://127.0.0.1",
                tooltip="Pixel Streaming URL. In UE5: enable Pixel Streaming plugin, "
                        "then toolbar > Stream Level Editor.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="viewport",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={"url": "http://127.0.0.1", "screenshot": ""},
                tooltip="Live UE5 viewport",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="UE5ViewportV2", library="UE5 Camera Control Library")},
            )
        )

        self.add_parameter(
            Parameter(
                name="screenshot",
                output_type="str",
                tooltip="Captured screenshot as base64 PNG data URL. Click Capture in the widget.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "stream_url" and value:
            url = str(value).strip()
            if url:
                viewport = dict(self.parameter_values.get("viewport") or {})
                viewport["url"] = url
                viewport.setdefault("screenshot", "")
                self.parameter_values["viewport"] = viewport
                self.parameter_output_values["viewport"] = dict(viewport)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        viewport_data = dict(self.parameter_values.get("viewport") or {})
        url = str(self.parameter_values.get("stream_url") or "").strip() or str(viewport_data.get("url", "")).strip()

        viewport_data["url"] = url
        viewport_data.setdefault("screenshot", "")

        self.parameter_output_values["viewport"] = viewport_data

        screenshot = viewport_data.get("screenshot", "") or ""
        self.parameter_output_values["screenshot"] = screenshot

        if screenshot:
            size_kb = len(screenshot) * 3 / 4 / 1024
            logger.info("UE5Viewport: Screenshot captured (%.0f KB)", size_kb)
