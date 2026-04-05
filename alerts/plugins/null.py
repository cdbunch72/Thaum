# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/null.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from alerts.base import BaseAlertPlugin, BaseAlertPluginConfig
from thaum.types import AlertPriority, ServerConfig, ThaumPerson


class NullAlertPluginConfig(BaseAlertPluginConfig):
    plugin: str = "null"


class NullAlertPlugin(BaseAlertPlugin):
    """No-op alert integration when send_alerts is disabled."""

    def validate_connection(self) -> bool:
        return True
    # -- End Method validate_connection

    def trigger_alert(
        self,
        summary: str,
        room_id: str,
        sender: ThaumPerson,
        priority=AlertPriority.NORMAL,
    ) -> Tuple[str, Optional[str]]:
        return ("", None)
    # -- End Method trigger_alert
# -- End Class NullAlertPlugin


def get_config_model():
    return NullAlertPluginConfig


def create_instance_plugin(config: NullAlertPluginConfig) -> NullAlertPlugin:
    return NullAlertPlugin(config)


def maintenance_tasks_register(registry: Any, *, server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    return
