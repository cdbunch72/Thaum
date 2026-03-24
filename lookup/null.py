# lookup/null.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from typing import List, Optional, Any

from pydantic import BaseModel

from lookup.base import BaseLookupPlugin
from lookup.base import BaseLookupPluginConfig
from thaum.types import ThaumPerson, ThaumTeam


class NullLookupPlugin(BaseLookupPlugin):
    """
    No remote identity backend.
    Uses BaseLookupPlugin SQLAlchemy cache only.
    """

    plugin_name = "null"

    def __init__(self, **config: Any):
        cfg = NullLookupPluginConfig(**config)
        super().__init__(
            db_url=cfg.db_url,
            cache_lock_path=cfg.cache_lock_path,
            default_team_ttl_seconds=cfg.default_team_ttl_seconds,
        )

    def fetch_team_members(self, team: ThaumTeam) -> List[ThaumPerson]:
        # Null backend cannot refresh members from an external source.
        return list(getattr(team, "_members", []))

# -- End Class NullLookupPlugin


def create_instance_lookup(config_raw: dict) -> NullLookupPlugin:
    return NullLookupPlugin(**(config_raw or {}))


class NullLookupPluginConfig(BaseLookupPluginConfig):
    # No additional fields; inherits cache settings.
    pass

# -- End Class NullLookupPluginConfig

