"""Blender Connect node - test connection to a Blender HTTP bridge."""

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger(__name__)


def _normalize_host(host: str) -> str:
    raw = (host or "").strip()
    if not raw:
        return "127.0.0.1"
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.hostname or "127.0.0.1"
    return raw.strip().strip("/")


class BlenderConnect(ControlNode):
    """Verify connectivity to a Blender bridge service."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "BlenderCamera",
            "description": "Test connection to Blender HTTP bridge",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="host",
                input_types=["str"],
                type="str",
                default_value="127.0.0.1",
                tooltip="Bridge host address",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="port",
                input_types=["int"],
                type="int",
                default_value=8765,
                tooltip="Bridge HTTP port",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="connected",
                output_type="bool",
                tooltip="True when bridge is reachable",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="connection_url",
                output_type="str",
                tooltip="Bridge base URL",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status_message",
                output_type="str",
                tooltip="Connection status details",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="bridge_config",
                output_type="dict",
                tooltip="Shared bridge config for downstream Blender nodes",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        host = _normalize_host(str(self.parameter_values.get("host", "127.0.0.1")))
        port = int(self.parameter_values.get("port", 8765))
        base_url = f"http://{host}:{port}"

        self.parameter_output_values["connection_url"] = base_url
        self.parameter_output_values["bridge_config"] = {
            "host": host,
            "port": port,
            "connection_url": base_url,
            "connected": False,
        }

        # Strict validation: this must be our Blender bridge service, not the web UI port.
        try:
            response = requests.get(f"{base_url}/health", timeout=3)
            response.raise_for_status()
            payload = response.json() if response.text else {}
            ok = bool(payload.get("ok")) if isinstance(payload, dict) else False
            message = str(payload.get("message", "")) if isinstance(payload, dict) else ""
            if ok and "Blender bridge alive" in message:
                self.parameter_output_values["connected"] = True
                self.parameter_output_values["status_message"] = (
                    f"Connected to Blender bridge at {base_url}/health ({message})"
                )
                self.parameter_output_values["bridge_config"] = {
                    "host": host,
                    "port": port,
                    "connection_url": base_url,
                    "connected": True,
                }
                return
        except requests.RequestException:
            pass
        except Exception as exc:
            logger.warning("Blender connect parse error: %s", exc)

        self.parameter_output_values["connected"] = False
        self.parameter_output_values["status_message"] = (
            f"Cannot verify Blender bridge at {base_url}/health. "
            "Use bridge port 8765 and run blender_bridge_server.py in Blender."
        )
        self.parameter_output_values["bridge_config"] = {
            "host": host,
            "port": port,
            "connection_url": base_url,
            "connected": False,
        }
