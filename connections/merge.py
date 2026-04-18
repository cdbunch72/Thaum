# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# connections/merge.py
"""Merge ``[connections.<name>]`` into consumer config dicts when ``connection_ref`` is set."""
from __future__ import annotations

from typing import Any, Dict

from plugin_loader import ensure_plugin_loaded, get_connection_plugin_config_model


def merge_connection_profile(full_config: Dict[str, Any], consumer: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge ``[connections.<name>]`` into *consumer* when ``connection_ref`` is set.

    Merge order: connection profile → *consumer* (consumer overrides on key conflicts).
    Removes ``connection_ref`` from the result. Drops ``plugin`` from the connection payload.
    """
    ref = consumer.get("connection_ref")
    if ref is None or (isinstance(ref, str) and not ref.strip()):
        return consumer
    ref_key = str(ref).strip()
    connections = full_config.get("connections")
    if not isinstance(connections, dict):
        raise ValueError("[connections] must be a table when connection_ref is set.")
    if ref_key not in connections:
        raise ValueError(
            f"connection_ref {ref_key!r} not found under [connections]. "
            f"Available: {sorted(connections.keys())!r}"
        )
    conn_raw = connections[ref_key]
    if not isinstance(conn_raw, dict):
        raise ValueError(f"[connections.{ref_key}] must be a table.")
    conn_plugin = str(conn_raw.get("plugin") or "atlassian")
    ensure_plugin_loaded("connections", conn_plugin)
    conn_model = get_connection_plugin_config_model(conn_plugin)
    validated_conn = conn_model(**conn_raw)
    base = validated_conn.model_dump(mode="python")
    base.pop("plugin", None)
    out: Dict[str, Any] = {**base, **consumer}
    out.pop("connection_ref", None)
    return out
