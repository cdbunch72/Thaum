# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/__init__.py
from __future__ import annotations

from typing import Any, Dict

from alerts.plugins.jira.config import JiraAlertPluginConfig
from thaum.types import ServerConfig
from alerts.plugins.jira.plugin import JiraPlugin


def get_config_model():
    return JiraAlertPluginConfig
# -- End Function get_config_model


def create_instance_plugin(config: JiraAlertPluginConfig) -> JiraPlugin:
    return JiraPlugin(config)
# -- End Function create_instance_plugin


def maintenance_tasks_register(registry: Any, *, server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    return
# -- End Function maintenance_tasks_register


__all__ = [
    "JiraAlertPluginConfig",
    "JiraPlugin",
    "create_instance_plugin",
    "get_config_model",
]
