# alerts/plugins/jira.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from typing import Optional

from pydantic import ConfigDict

from alerts.base import BaseAlertPlugin, BaseAlertPluginConfig
from thaum.types import AlertPriority, ResolvedSecret, ThaumPerson


class JiraAlertPluginConfig(BaseAlertPluginConfig):
    plugin: str = "jira"
    base_url: str
    user: str
    api_token: ResolvedSecret
    responders: list[str]
    priority_normal: str = "P3"
    priority_high: str = "P2"
    status_webhook_bearer: str

    model_config = ConfigDict(extra="allow")
# -- End Class JiraAlertPluginConfig


class JiraPlugin(BaseAlertPlugin):
    supports_status_webhooks: bool = True

    def __init__(self, config: JiraAlertPluginConfig):
        super().__init__(config)
        self.cfg = config
    # -- End Method __init__

    def validate_status_webhook_authorization(self, authorization_header_value: Optional[str]) -> bool:
        """Jira status webhooks: static Bearer using canonical JSON, or disabled when config is ''."""
        return self._validate_static_webhook_bearer(
            authorization_header_value,
            self.cfg.status_webhook_bearer,
        )
    # -- End Method validate_status_webhook_authorization

    def validate_connection(self) -> bool:
        # Placeholder until Jira API probe is implemented.
        return True
    # -- End Method validate_connection

    def trigger_alert(
        self,
        summary: str,
        room_id: str,
        sender: ThaumPerson,
        priority=AlertPriority.NORMAL,
    ) -> tuple[str, str]:
        """
        TODO: Implement Jira API POST and return (short_id, jira_alert_id).
        """
        short_id = self._generate_short_id(4)
        severity = self.cfg.priority_high if priority == AlertPriority.HIGH else self.cfg.priority_normal
        self.logger.info("Jira trigger not implemented yet: severity=%s summary=%s", severity, summary)
        return short_id, ""
    # -- End Method trigger_alert


def get_config_model():
    return JiraAlertPluginConfig
# -- End Function get_config_model


def create_instance_plugin(config: JiraAlertPluginConfig) -> JiraPlugin:
    return JiraPlugin(config)
# -- End Function create_instance_plugin

