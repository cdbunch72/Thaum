# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/config.py
from __future__ import annotations

from pydantic import ConfigDict, Field

from alerts.base import BaseAlertPluginConfig
from thaum.types import ResolvedSecret

_DEFAULT_STATUS_ACK = (
    "{{ responder_mention }} has acknowledged the alert and should be joining you shortly. "
    "Allow time to login."
)
_DEFAULT_STATUS_UNACK = (
    "{{ responder_mention }} is not able to help you after all, escalating to next level. "
    "Thank you for your patience."
)
_DEFAULT_STATUS_ESCALATE = "The alert has been escalated, thank you for your patience."


class JiraAlertPluginConfig(BaseAlertPluginConfig):
    """Status Jinja templates get: team_description, sender_*, responder_* (see status_webhook)."""

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
    status_ack_template: str = Field(default=_DEFAULT_STATUS_ACK)
    status_unack_template: str = Field(default=_DEFAULT_STATUS_UNACK)
    status_escalate_template: str = Field(default=_DEFAULT_STATUS_ESCALATE)

    model_config = ConfigDict(extra="allow")
# -- End Class JiraAlertPluginConfig
