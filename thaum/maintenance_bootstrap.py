# thaum/maintenance_bootstrap.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import logging
from typing import Any, Dict

from plugin_loader import ensure_plugin_loaded

from thaum import leader_service
from thaum.types import LogLevel, ServerConfig

logger = logging.getLogger("thaum.maintenance_bootstrap")


def register_all_maintenance_tasks(server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    """Call ``maintenance_tasks_register`` on lookup, bot, alert plugins, then builtins."""
    lookup_type = server_cfg.lookup_plugin
    bot_type = server_cfg.bot_type
    alert_types: set[str] = {"null"}
    for row in (config.get("bots") or {}).values():
        if isinstance(row, dict):
            alert_types.add(str(row.get("alert_type", "null")))

    for kind, name in (
        ("lookup", lookup_type),
        ("bots", bot_type),
    ):
        mod = ensure_plugin_loaded(kind, name)
        reg = getattr(mod, "maintenance_tasks_register", None)
        if reg is not None:
            reg(leader_service, server_cfg=server_cfg, config=config)

    for at in sorted(alert_types):
        mod = ensure_plugin_loaded("alerts", at)
        reg = getattr(mod, "maintenance_tasks_register", None)
        if reg is not None:
            reg(leader_service, server_cfg=server_cfg, config=config)

    from thaum import builtin_leader_tasks

    builtin_leader_tasks.register_builtin_tasks(leader_service, server_cfg=server_cfg, config=config)
    logger.log(LogLevel.VERBOSE, "Leader maintenance task registration complete")
