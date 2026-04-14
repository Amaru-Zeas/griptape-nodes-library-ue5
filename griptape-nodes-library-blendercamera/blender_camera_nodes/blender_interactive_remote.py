"""Blender Interactive Remote node - embed interactive remote UI URL."""

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget


class BlenderInteractiveRemoteNode(DataNode):
    """Render an interactive remote Blender session URL in a node widget."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "BlenderCamera",
            "description": "Embed an interactive remote Blender session URL",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="session_url",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="URL of your interactive remote Blender session (WebRTC/Kasm/Guac/noVNC web client)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="remote_view",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={"url": ""},
                tooltip="Interactive remote frame",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="BlenderInteractiveRemote", library="Blender Camera Control Library")},
            )
        )
        self.add_parameter(
            Parameter(
                name="current_url",
                output_type="str",
                tooltip="Current remote session URL shown in the widget",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "session_url" and value:
            url = str(value).strip()
            self.parameter_values["remote_view"] = {"url": url}
            self.parameter_output_values["remote_view"] = {"url": url}
            self.parameter_output_values["current_url"] = url
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        direct = str(self.parameter_values.get("session_url", "")).strip()
        remote_data = self.parameter_values.get("remote_view", {})

        url = direct
        if not url and isinstance(remote_data, dict):
            url = str(remote_data.get("url", "")).strip()

        data = {"url": url}
        self.parameter_output_values["remote_view"] = data
        self.parameter_values["remote_view"] = data
        self.parameter_output_values["current_url"] = url
