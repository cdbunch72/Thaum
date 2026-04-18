# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# lookup/factory.py
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from connections.merge import merge_connection_profile
from lookup.base import BaseLookupPlugin
from plugin_loader import ensure_plugin_loaded

logger = logging.getLogger("lookup.factory")


def merge_lookup_connection_profile(full_config: Dict[str, Any], merged_lookup: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge ``[connections.<name>]`` into lookup plugin settings when ``connection_ref`` is set.

    Merge order: connection profile → keys already in *merged_lookup* (lookup + lookup.<type>).
    Removes ``connection_ref`` from the result. Drops ``plugin`` from the connection payload
    so it does not collide with consumer models.
    """
    return merge_connection_profile(full_config, merged_lookup)


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
