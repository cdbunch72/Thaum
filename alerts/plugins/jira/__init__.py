# alerts/plugins/jira/__init__.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from alerts.plugins.jira.config import JiraAlertPluginConfig
from alerts.plugins.jira.plugin import JiraPlugin


def get_config_model():
    return JiraAlertPluginConfig
# -- End Function get_config_model


def create_instance_plugin(config: JiraAlertPluginConfig) -> JiraPlugin:
    return JiraPlugin(config)
# -- End Function create_instance_plugin


__all__ = [
    "JiraAlertPluginConfig",
    "JiraPlugin",
    "create_instance_plugin",
    "get_config_model",
]
