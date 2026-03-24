# lookup/factory.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import importlib
import logging
import os
from typing import Any

from lookup.base import BaseLookupPlugin

logger = logging.getLogger("lookup.factory")


def create_lookup(lookup_type: str, config_raw: dict[str, Any]) -> BaseLookupPlugin:
    """
    Dynamically load a lookup plugin module and build one instance.
    """
    try:
        module = importlib.import_module(f"lookup.{lookup_type}")
        factory_func = getattr(module, "create_instance_lookup")
        # Support TOML shape:
        #   [lookup]
        #   db_url = "..."
        #   [lookup.<plugin_name>]
        #   ...
        plugin_cfg = config_raw.get(lookup_type, {}) if isinstance(config_raw, dict) else {}
        merged_cfg: dict[str, Any] = dict(config_raw or {})
        if isinstance(plugin_cfg, dict):
            merged_cfg.update(plugin_cfg)

        lookup = factory_func(merged_cfg)
        if not isinstance(lookup, BaseLookupPlugin):
            raise TypeError(f"Lookup '{lookup_type}' is not a BaseLookupPlugin descendant")
        return lookup
    except ImportError as e:
        lookup_dir = os.path.join(os.path.dirname(__file__), ".")
        ignore_files = {"base.py", "factory.py", "instance.py", "__init__.py"}
        available = [
            f.replace(".py", "")
            for f in os.listdir(lookup_dir)
            if f.endswith(".py") and f not in ignore_files
        ]
        logger.critical(f"Failed to load lookup plugin '{lookup_type}': {e}")
        raise ValueError(f"Lookup plugin '{lookup_type}' not found. Available: {available}")

# -- End Function create_lookup

