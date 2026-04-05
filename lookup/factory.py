# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# lookup/factory.py
from __future__ import annotations

import logging
import os
from typing import Any

from lookup.base import BaseLookupPlugin
from plugin_loader import ensure_plugin_loaded

logger = logging.getLogger("lookup.factory")


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
