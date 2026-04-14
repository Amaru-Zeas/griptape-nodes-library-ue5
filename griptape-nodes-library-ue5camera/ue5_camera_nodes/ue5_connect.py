"""UE5 Connect node - test connection to Unreal Engine 5's Remote Control API."""

import logging
from typing import Any

import requests

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger(__name__)


class UE5Connect(ControlNode):
    """Test and verify connection to a running Unreal Engine 5 instance.

    UE5 must have the **Remote Control API** plugin enabled
    (Edit > Plugins > search "Remote Control API").

    The plugin exposes an HTTP API on port 30010 by default.
    This node pings the /remote/info endpoint to verify the connection
    and outputs the connection URL for downstream camera control nodes.
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "UE5Connection",
            "description": "Test connection to UE5 Remote Control API",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        # --- Inputs ---
        self.add_parameter(
            Parameter(
                name="host",
                input_types=["str"],
                type="str",
                default_value="localhost",
                tooltip="UE5 host address (usually localhost)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="port",
                input_types=["int"],
                type="int",
                default_value=30010,
                tooltip="UE5 Remote Control API port (default 30010)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # --- Outputs ---
        self.add_parameter(
            Parameter(
                name="connected",
                output_type="bool",
                tooltip="True if UE5 is reachable",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="connection_url",
                output_type="str",
                tooltip="Base URL for the UE5 Remote Control API (e.g. http://localhost:30010)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status_message",
                output_type="str",
                tooltip="Human-readable connection status",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        host = str(self.parameter_values.get("host", "localhost")).strip()
        port = int(self.parameter_values.get("port", 30010))
        base_url = f"http://{host}:{port}"

        try:
            # The Remote Control API exposes GET /remote/info
            resp = requests.get(f"{base_url}/remote/info", timeout=5)
            resp.raise_for_status()

            info = resp.json() if resp.text else {}
            logger.info("UE5 Remote Control API connected: %s", info)

            self.parameter_output_values["connected"] = True
            self.parameter_output_values["connection_url"] = base_url

            # Build a friendly status message
            engine_ver = info.get("EngineVersion", "unknown")
            plugins = info.get("ActivePresets", [])
            msg = f"Connected to UE5 (v{engine_ver}) at {base_url}"
            if plugins:
                msg += f" | Presets: {', '.join(plugins)}"
            self.parameter_output_values["status_message"] = msg

        except requests.ConnectionError:
            logger.warning("Cannot reach UE5 at %s - is UE5 running with Remote Control API enabled?", base_url)
            self.parameter_output_values["connected"] = False
            self.parameter_output_values["connection_url"] = base_url
            self.parameter_output_values["status_message"] = (
                f"Cannot reach UE5 at {base_url}. "
                "Make sure UE5 is running and the Remote Control API plugin is enabled."
            )
        except requests.Timeout:
            logger.warning("Connection to UE5 at %s timed out", base_url)
            self.parameter_output_values["connected"] = False
            self.parameter_output_values["connection_url"] = base_url
            self.parameter_output_values["status_message"] = (
                f"Connection timed out at {base_url}. UE5 may be loading or unresponsive."
            )
        except Exception as exc:
            logger.error("Unexpected error connecting to UE5: %s", exc)
            self.parameter_output_values["connected"] = False
            self.parameter_output_values["connection_url"] = base_url
            self.parameter_output_values["status_message"] = f"Error: {exc}"
