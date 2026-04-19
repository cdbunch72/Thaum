# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/maintenance_bootstrap.py
from __future__ import annotations

import logging
from typing import Any, Dict

from plugin_loader import ensure_plugin_loaded

from thaum import leader_init
from thaum import leader_service
from thaum.types import LogLevel, ServerConfig

logger = logging.getLogger("thaum.maintenance_bootstrap")


def register_all_leader_init_tasks(server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    """Call ``leader_init_tasks_register`` on lookup, bot, and alert plugins (one-shot bootstrap hooks)."""
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
        reg = getattr(mod, "leader_init_tasks_register", None)
        if reg is not None:
            logger.log(
                LogLevel.VERBOSE,
                "Leader init: registering tasks from %s plugin %r",
                kind,
                name,
            )
            reg(leader_init, server_cfg=server_cfg, config=config)

    for at in sorted(alert_types):
        mod = ensure_plugin_loaded("alerts", at)
        reg = getattr(mod, "leader_init_tasks_register", None)
        if reg is not None:
            logger.log(
                LogLevel.VERBOSE,
                "Leader init: registering tasks from alerts plugin %r",
                at,
            )
            reg(leader_init, server_cfg=server_cfg, config=config)

    logger.log(LogLevel.VERBOSE, "Leader init task registration complete")


def register_all_leader_post_bots_init_tasks(server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    """Call ``leader_post_bots_init_tasks_register`` on lookup, bot, and alert plugins (after ``initialize_bots``)."""
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
        reg = getattr(mod, "leader_post_bots_init_tasks_register", None)
        if reg is not None:
            logger.log(
                LogLevel.VERBOSE,
                "Leader post-bots init: registering tasks from %s plugin %r",
                kind,
                name,
            )
            reg(leader_init, server_cfg=server_cfg, config=config)

    for at in sorted(alert_types):
        mod = ensure_plugin_loaded("alerts", at)
        reg = getattr(mod, "leader_post_bots_init_tasks_register", None)
        if reg is not None:
            logger.log(
                LogLevel.VERBOSE,
                "Leader post-bots init: registering tasks from alerts plugin %r",
                at,
            )
            reg(leader_init, server_cfg=server_cfg, config=config)

    logger.log(LogLevel.VERBOSE, "Leader post-bots init task registration complete")


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
            logger.log(
                LogLevel.VERBOSE,
                "Leader maintenance: invoking %s plugin %r maintenance_tasks_register",
                kind,
                name,
            )
            reg(leader_service, server_cfg=server_cfg, config=config)

    for at in sorted(alert_types):
        mod = ensure_plugin_loaded("alerts", at)
        reg = getattr(mod, "maintenance_tasks_register", None)
        if reg is not None:
            logger.log(
                LogLevel.VERBOSE,
                "Leader maintenance: invoking alerts plugin %r maintenance_tasks_register",
                at,
            )
            reg(leader_service, server_cfg=server_cfg, config=config)

    from thaum import builtin_leader_tasks

    logger.log(LogLevel.VERBOSE, "Leader maintenance: registering builtin tasks")
    builtin_leader_tasks.register_builtin_tasks(leader_service, server_cfg=server_cfg, config=config)
    logger.log(LogLevel.VERBOSE, "Leader maintenance task registration complete")

    register_all_leader_init_tasks(server_cfg, config)
    register_all_leader_post_bots_init_tasks(server_cfg, config)
