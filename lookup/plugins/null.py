# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# lookup/plugins/null.py
from __future__ import annotations

from typing import Any, Dict, List

from lookup.base import BaseLookupPlugin, BaseLookupPluginConfig
from thaum.types import ServerConfig, ThaumPerson, ThaumTeam


class NullLookupPlugin(BaseLookupPlugin):
    """
    No remote identity backend.
    Uses BaseLookupPlugin persistence on :class:`gemstone_utils.db.GemstoneDB` only.
    """

    plugin_name = "null"

    def __init__(self, **config: Any):
        cfg = NullLookupPluginConfig(**config)
        super().__init__(
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


def get_config_model():
    return NullLookupPluginConfig


def maintenance_tasks_register(registry: Any, *, server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    return

