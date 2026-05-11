from __future__ import annotations

from datetime import datetime
import logging
from typing import Any
from urllib.parse import quote, urlencode

import requests

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.widget import Widget

logger = logging.getLogger(__name__)


class StoryPromptSelectorNode(DataNode):
    """Expose prompt selected by StoryPromptPickerWidget."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None, **kwargs) -> None:
        node_metadata = {
            "category": "StoryPrompt",
            "description": "Pick and output recent prompts from Story Pipeline.",
        }
        if metadata:
            node_metadata.update(metadata)
        super().__init__(name=name, metadata=node_metadata, **kwargs)

        self.add_parameter(
            Parameter(
                name="api_base_url",
                input_types=["str"],
                type="str",
                default_value="http://localhost:3000",
                tooltip="Story Pipeline base URL.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="prompts_endpoint",
                input_types=["str"],
                type="str",
                default_value="/api/prompts",
                tooltip="Endpoint path for recent prompts.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="project_id",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Story Pipeline project ID used by GET /api/prompts.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="limit",
                input_types=["int"],
                type="int",
                default_value=20,
                tooltip="Maximum recent prompts to fetch.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="selected_prompt_id",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Optional selected prompt id override.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="request_timeout_seconds",
                input_types=["float"],
                type="float",
                default_value=8.0,
                tooltip="HTTP timeout in seconds.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt_selector",
                input_types=["dict"],
                type="dict",
                output_type="dict",
                default_value={
                    "apiBaseUrl": "http://localhost:3000",
                    "promptsEndpoint": "/api/prompts",
                    "projectId": "",
                    "limit": 20,
                    "selectedPromptId": "",
                    "selectedPromptLabel": "",
                    "selectedPromptText": "",
                    "items": [],
                    "statusMessage": "Set project ID and click Update.",
                    "refreshNonce": 0,
                    "lastSyncedAt": "",
                    "autoFetchOnOpen": False,
                },
                tooltip="Dropdown + Update button UI for Story prompts.",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="StoryPromptPickerWidget", library="Story Prompt Library")},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt_text",
                output_type="str",
                tooltip="Selected prompt text.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt_id",
                output_type="str",
                tooltip="Selected prompt id.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt_label",
                output_type="str",
                tooltip="Selected prompt display label.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt_item",
                output_type="dict",
                tooltip="Selected prompt item payload.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="prompts_payload",
                output_type="dict",
                tooltip="Fetched prompts list payload ({items:[...]}).",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="status_message",
                output_type="str",
                tooltip="Fetch/select status.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    @staticmethod
    def _format_created_at(value: Any) -> str:
        if not value:
            return "unknown"
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.strftime("%b %d %H:%M")
        except ValueError:
            return text

    def _build_label(self, item: dict[str, Any]) -> str:
        entity_type = str(item.get("entityType") or "UNKNOWN").upper()
        entity_name = str(item.get("entityName") or "Unnamed")
        prompt_type = str(item.get("promptType") or "custom")
        created = self._format_created_at(item.get("createdAt"))
        return f"[{entity_type}] {entity_name} · {prompt_type} · {created}"

    @staticmethod
    def _extract_widget_state(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def _safe_text(value: Any) -> str:
        return str(value or "").strip()

    def _build_prompts_url(self, base_url: str, endpoint: str, project_id: str, limit: int) -> str:
        base = base_url.rstrip("/")
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        query = urlencode({"projectId": project_id, "limit": max(1, min(100, limit))})
        return f"{base}{path}?{query}"

    def _build_project_url(self, base_url: str, project_id: str) -> str:
        base = base_url.rstrip("/")
        return f"{base}/api/projects/{quote(project_id, safe='')}"

    def _normalize_prompt_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": self._safe_text(item.get("id")),
            "entityName": self._safe_text(item.get("entityName")) or "Unnamed",
            "entityType": self._safe_text(item.get("entityType")) or "UNKNOWN",
            "promptType": self._safe_text(item.get("promptType")) or "custom",
            "promptText": self._safe_text(item.get("promptText")),
            "status": self._safe_text(item.get("status")) or "generated",
            "createdAt": self._safe_text(item.get("createdAt")),
        }

    def _extract_prompt_text_from_entity(self, entity: dict[str, Any]) -> tuple[str, str]:
        draft = self._safe_text(entity.get("draftContent"))
        if draft:
            return draft, "draft"

        canon = self._safe_text(entity.get("canonData"))
        if canon:
            return canon, "canon"

        messages = entity.get("messages")
        if isinstance(messages, list):
            for msg in reversed(messages):
                if not isinstance(msg, dict):
                    continue
                content = self._safe_text(msg.get("content"))
                if content:
                    role = self._safe_text(msg.get("role")) or "message"
                    return content, role
        return "", ""

    def _derive_items_from_project(self, project: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        entities = project.get("entities")
        if not isinstance(entities, list):
            return []

        normalized: list[dict[str, Any]] = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            prompt_text, prompt_type = self._extract_prompt_text_from_entity(entity)
            if not prompt_text:
                continue
            entity_id = self._safe_text(entity.get("id"))
            if not entity_id:
                continue

            normalized.append(
                {
                    "id": f"entity:{entity_id}",
                    "entityName": self._safe_text(entity.get("name")) or "Unnamed",
                    "entityType": self._safe_text(entity.get("type")) or "UNKNOWN",
                    "promptType": prompt_type or "derived",
                    "promptText": prompt_text,
                    "status": "derived",
                    "createdAt": self._safe_text(entity.get("updatedAt"))
                    or self._safe_text(entity.get("createdAt"))
                    or self._safe_text(project.get("updatedAt"))
                    or self._safe_text(project.get("createdAt")),
                }
            )

        normalized.sort(key=lambda item: self._safe_text(item.get("createdAt")), reverse=True)
        return normalized[: max(1, min(100, limit))]

    def _fetch_items(
        self, api_base_url: str, prompts_endpoint: str, project_id: str, limit: int, timeout_s: float
    ) -> tuple[list[dict[str, Any]], str]:
        timeout_s = max(0.5, timeout_s)
        headers = {"Accept": "application/json"}
        prompts_url = self._build_prompts_url(api_base_url, prompts_endpoint, project_id, limit)
        project_url = self._build_project_url(api_base_url, project_id)

        try:
            response = requests.get(prompts_url, headers=headers, timeout=timeout_s)
            if response.ok:
                payload = response.json()
                raw_items = payload.get("items", []) if isinstance(payload, dict) else []
                if not isinstance(raw_items, list):
                    raw_items = []
                items = [
                    self._normalize_prompt_item(item)
                    for item in raw_items
                    if isinstance(item, dict) and self._safe_text(item.get("promptText"))
                ]
                return items[: max(1, min(100, limit))], f"Loaded {len(items)} prompt(s)."
        except Exception as exc:
            logger.warning("GET %s failed: %s", prompts_url, exc)

        # Compatibility fallback for Story Pipeline installs that don't expose /api/prompts.
        try:
            response = requests.get(project_url, headers=headers, timeout=timeout_s)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return [], "Project API returned an unexpected payload."
            items = self._derive_items_from_project(payload, limit)
            return items, f"Loaded {len(items)} prompt(s) from project data."
        except Exception as exc:
            logger.warning("Fallback GET %s failed: %s", project_url, exc)
            return [], f"Update failed: {exc}"

    def process(self) -> None:
        widget_state = self._extract_widget_state(self.parameter_values.get("prompt_selector", {}))

        api_base_url = str(self.parameter_values.get("api_base_url", "http://localhost:3000")).strip()
        prompts_endpoint = str(self.parameter_values.get("prompts_endpoint", "/api/prompts")).strip()
        project_id = str(self.parameter_values.get("project_id", "")).strip()
        limit = int(self.parameter_values.get("limit", 20))
        timeout_s = float(self.parameter_values.get("request_timeout_seconds", 8.0))
        selected_prompt_id = str(self.parameter_values.get("selected_prompt_id", "")).strip()

        if not project_id:
            project_id = str(widget_state.get("projectId", "")).strip()
        if not selected_prompt_id:
            selected_prompt_id = str(widget_state.get("selectedPromptId", "")).strip()

        cached_items = widget_state.get("items", [])
        items: list[dict[str, Any]] = cached_items if isinstance(cached_items, list) else []
        status_message = str(widget_state.get("statusMessage", "")).strip()
        if not status_message:
            status_message = "Ready."

        if project_id:
            items, status_message = self._fetch_items(
                api_base_url=api_base_url,
                prompts_endpoint=prompts_endpoint,
                project_id=project_id,
                limit=limit,
                timeout_s=timeout_s,
            )
        else:
            status_message = "Project ID is required."

        selected_item: dict[str, Any] | None = None
        if selected_prompt_id:
            selected_item = next((item for item in items if str(item.get("id", "")).strip() == selected_prompt_id), None)

        if selected_item is None and items:
            selected_item = items[0]

        prompt_text = ""
        prompt_id = ""
        prompt_label = ""
        if selected_item:
            prompt_text = str(selected_item.get("promptText") or "")
            prompt_id = str(selected_item.get("id") or "")
            prompt_label = self._build_label(selected_item)

        widget_payload = {
            "apiBaseUrl": api_base_url,
            "promptsEndpoint": prompts_endpoint,
            "projectId": project_id,
            "limit": limit,
            "selectedPromptId": prompt_id,
            "selectedPromptLabel": prompt_label,
            "selectedPromptText": prompt_text,
            "items": items,
            "statusMessage": status_message,
            "refreshNonce": int(widget_state.get("refreshNonce", 0) or 0),
            "lastSyncedAt": str(widget_state.get("lastSyncedAt", "")),
            "autoFetchOnOpen": bool(widget_state.get("autoFetchOnOpen", False)),
        }

        self.parameter_output_values["prompt_selector"] = widget_payload
        self.parameter_output_values["prompt_text"] = prompt_text
        self.parameter_output_values["prompt_id"] = prompt_id
        self.parameter_output_values["prompt_label"] = prompt_label
        self.parameter_output_values["prompt_item"] = selected_item or {}
        self.parameter_output_values["prompts_payload"] = {"items": items}
        self.parameter_output_values["status_message"] = status_message
