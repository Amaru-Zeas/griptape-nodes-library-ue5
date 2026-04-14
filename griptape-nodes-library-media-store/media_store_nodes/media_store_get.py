"""Media Store Get node."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.widget import Widget

import media_store_registry as _registry


class MediaStoreGetNode(ControlNode):
    """Fetch text/media previously saved by Media Store Set nodes."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "MediaStore",
            "description": "Get stored text/image/video/audio by key",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="selector",
                input_types=["dict"],
                type="dict",
                default_value={
                    "keys": [],
                    "selectedKey": "",
                    "status": "No values saved yet.",
                    "mediaType": "",
                    "anyOutput": "",
                    "preview": "",
                    "refreshTick": 0,
                },
                tooltip="Select one of the saved keys from dropdown.",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Widget(name="MediaStoreSelector", library="Media Store Library")},
            )
        )
        self.add_parameter(
            Parameter(
                name="any_output",
                output_type="str",
                tooltip="Stored value regardless of media type",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        # Always rebuild from live Set nodes so deleted nodes disappear on refresh/play.
        get_live_entries_fn = getattr(_registry, "get_live_entries", None)
        if callable(get_live_entries_fn):
            entries = get_live_entries_fn()
        else:
            refresh_fn = (
                getattr(_registry, "refresh_store_from_live_nodes", None)
                or getattr(_registry, "refesh_store_from_live_nodes", None)
            )
            if callable(refresh_fn):
                refresh_fn()
            keys = _registry.list_keys()
            entries = {k: (_registry.get_entry(k) or {}) for k in keys}

        keys = sorted(entries.keys())
        selector = self.parameter_values.get("selector", {})
        selector = selector if isinstance(selector, dict) else {}

        selected = str(selector.get("selectedKey", "") or "").strip()
        key = selected
        if key not in keys and keys:
            key = keys[0]

        entry = entries.get(key) if key else None
        value = str(entry.get("value", "") if entry else "")
        media_type = str(entry.get("media_type", "") if entry else "")

        status = f"Loaded '{key}'." if entry else "Key not found. Run Set first."
        out_selector = {
            "keys": keys,
            "selectedKey": key,
            "status": status,
            "mediaType": media_type,
            "anyOutput": value,
            "preview": value[:240],
            "refreshTick": int(selector.get("refreshTick", 0) or 0),
        }

        self.parameter_values["selector"] = out_selector
        self.parameter_output_values["any_output"] = value

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "selector":
            # Make Refresh and dropdown changes behave like a local re-run.
            self.process()
        return super().after_value_set(parameter, value)

