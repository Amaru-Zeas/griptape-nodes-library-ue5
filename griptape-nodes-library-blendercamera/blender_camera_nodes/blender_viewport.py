"""Blender Viewport node - embed a live viewport stream URL."""

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget


class BlenderViewportNode(DataNode):
    """Render a live stream URL in a node widget for Blender monitoring."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "BlenderCamera",
            "description": "Embed a live stream URL for Blender viewport",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="stream_url",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="URL of your Blender viewport stream (WebRTC/RTMP web player/etc.)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="viewport",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={"url": ""},
                tooltip="Interactive web viewport frame",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="BlenderViewport", library="Blender Camera Control Library")},
            )
        )
        self.add_parameter(
            Parameter(
                name="current_url",
                output_type="str",
                tooltip="Current stream URL shown in the widget",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "stream_url" and value:
            url = str(value).strip()
            self.parameter_values["viewport"] = {"url": url}
            self.parameter_output_values["viewport"] = {"url": url}
            self.parameter_output_values["current_url"] = url
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        direct = str(self.parameter_values.get("stream_url", "")).strip()
        viewport_data = self.parameter_values.get("viewport", {})

        url = direct
        if not url and isinstance(viewport_data, dict):
            url = str(viewport_data.get("url", "")).strip()

        data = {"url": url}
        self.parameter_output_values["viewport"] = data
        self.parameter_values["viewport"] = data
        self.parameter_output_values["current_url"] = url
