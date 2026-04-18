# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# lookup/factory.py
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from lookup.base import BaseLookupPlugin
from plugin_loader import ensure_plugin_loaded, get_connection_plugin_config_model

logger = logging.getLogger("lookup.factory")


def merge_lookup_connection_profile(full_config: Dict[str, Any], merged_lookup: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge ``[connections.<name>]`` into lookup plugin settings when ``connection_ref`` is set.

    Merge order: connection profile → keys already in *merged_lookup* (lookup + lookup.<type>).
    Removes ``connection_ref`` from the result. Drops ``plugin`` from the connection payload
    so it does not collide with consumer models.
    """
    ref = merged_lookup.get("connection_ref")
    if ref is None or (isinstance(ref, str) and not ref.strip()):
        return merged_lookup
    ref_key = str(ref).strip()
    connections = full_config.get("connections")
    if not isinstance(connections, dict):
        raise ValueError("[connections] must be a table when lookup.connection_ref is set.")
    if ref_key not in connections:
        raise ValueError(
            f"lookup connection_ref {ref_key!r} not found under [connections]. "
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
    out: Dict[str, Any] = {**base, **merged_lookup}
    out.pop("connection_ref", None)
    return out


def merged_lookup_plugin_config(lookup_type: str, lookup_raw: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ``[lookup]`` with ``[lookup.<type>]`` the same way bootstrap validates plugins."""
    plugin_cfg = lookup_raw.get(lookup_type, {}) if isinstance(lookup_raw, dict) else {}
    merged: Dict[str, Any] = dict(lookup_raw or {})
    if isinstance(plugin_cfg, dict):
        merged.update(plugin_cfg)
    return merged


def create_lookup(lookup_type: str, config_raw: dict[str, Any]) -> BaseLookupPlugin:
    """
    Dynamically load a lookup plugin module and build one instance from a plain dict.
    """
    try:
        module = ensure_plugin_loaded("lookup", lookup_type)
        factory_func = getattr(module, "create_instance_lookup")
        return factory_func(config_raw or {})
    except ImportError as e:
        lookup_dir = os.path.join(os.path.dirname(__file__), "plugins")
        ignore_files = {"__init__.py"}
        available = [
            f.replace(".py", "")
            for f in os.listdir(lookup_dir)
            if f.endswith(".py") and f not in ignore_files
        ]
        logger.critical("Failed to load lookup plugin '%s': %s", lookup_type, e)
        raise ValueError(f"Lookup plugin '{lookup_type}' not found. Available: {available}") from e
# -- End Function create_lookup
