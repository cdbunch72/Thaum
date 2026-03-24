# lookup/instance.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from typing import Any, Optional

from lookup.base import BaseLookupPlugin
from lookup.factory import create_lookup

LOOKUP_PLUGIN: Optional[BaseLookupPlugin] = None


def initialize_lookup_plugin(lookup_type: str, config_raw: dict[str, Any]) -> BaseLookupPlugin:
    """
    Build and store the single server-wide lookup plugin instance.
    """
    global LOOKUP_PLUGIN
    LOOKUP_PLUGIN = create_lookup(lookup_type, config_raw)
    return LOOKUP_PLUGIN

# -- End Function initialize_lookup_plugin


def get_lookup_plugin() -> BaseLookupPlugin:
    if LOOKUP_PLUGIN is None:
        raise RuntimeError("Lookup plugin is not initialized.")
    return LOOKUP_PLUGIN

# -- End Function get_lookup_plugin

