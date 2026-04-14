"""In-memory registry shared by Media Store nodes."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from weakref import WeakValueDictionary


@dataclass
class MediaEntry:
    key: str
    media_type: str
    value: str
    source_node: str
    updated_at: str


_LOCK = RLock()
_STORE: dict[str, MediaEntry] = {}
_LIVE_SET_NODES: "WeakValueDictionary[str, Any]" = WeakValueDictionary()


def _node_still_exists(node_name: str) -> bool:
    """Best-effort check against current GTN graph state."""
    try:
        from griptape_nodes.retained_mode.events.connection_events import (  # type: ignore[reportMissingImports]
            ListConnectionsForNodeRequest,
            ListConnectionsForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore[reportMissingImports]
    except Exception:
        # In non-engine contexts we cannot verify, so keep conservative behavior.
        return True

    try:
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=node_name))
    except Exception:
        return False
    return isinstance(result, ListConnectionsForNodeResultSuccess)


def upsert_entry(key: str, media_type: str, value: str, source_node: str) -> MediaEntry:
    entry = MediaEntry(
        key=key,
        media_type=media_type,
        value=value,
        source_node=source_node,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    with _LOCK:
        _STORE[key] = entry
    return entry


def get_entry(key: str) -> dict[str, Any] | None:
    with _LOCK:
        entry = _STORE.get(key)
    if not entry:
        return None
    return asdict(entry)


def list_keys() -> list[str]:
    with _LOCK:
        keys = sorted(_STORE.keys())
    return keys


def register_set_node(node_name: str, node_obj: Any) -> None:
    with _LOCK:
        _LIVE_SET_NODES[node_name] = node_obj


def refresh_store_from_live_nodes() -> None:
    """Rebuild store from currently live Media Store Set nodes.

    This removes stale keys left behind by deleted Set nodes.
    """
    rebuilt: dict[str, MediaEntry] = {}
    with _LOCK:
        live_items = list(_LIVE_SET_NODES.items())

    for node_name, node in live_items:
        if not _node_still_exists(node_name):
            continue
        try:
            entry_dict = node.export_entry()
        except Exception:
            continue
        key = str(entry_dict.get("key", "") or "").strip()
        if not key:
            continue
        rebuilt[key] = MediaEntry(
            key=key,
            media_type=str(entry_dict.get("media_type", "text") or "text"),
            value=str(entry_dict.get("value", "") or ""),
            source_node=str(entry_dict.get("source_node", "") or ""),
            updated_at=str(entry_dict.get("updated_at", datetime.now(timezone.utc).isoformat())),
        )

    with _LOCK:
        _STORE.clear()
        _STORE.update(rebuilt)


def refesh_store_from_live_nodes() -> None:
    """Backward-compatible alias for older typo imports."""
    refresh_store_from_live_nodes()


def get_live_entries() -> dict[str, dict[str, Any]]:
    """Return current entries derived directly from live Set nodes."""
    refresh_store_from_live_nodes()
    with _LOCK:
        snapshot = {k: asdict(v) for k, v in _STORE.items()}
    return snapshot

