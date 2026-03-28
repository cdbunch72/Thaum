# alerts/plugins/jira/config.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from pydantic import ConfigDict

from alerts.base import BaseAlertPluginConfig
from thaum.types import ResolvedSecret


class JiraAlertPluginConfig(BaseAlertPluginConfig):
    plugin: str = "jira"
    site_url: str
    cloud_id: str
    user: str
    api_token: ResolvedSecret
    responders: list[str]
    priority_normal: str = "P3"
    priority_high: str = "P2"
    status_webhook_bearer: str
    send_escalate_msg: bool = False

    model_config = ConfigDict(extra="allow")
# -- End Class JiraAlertPluginConfig
