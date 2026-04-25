# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/models.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from gemstone_utils.db import GemstoneDB


class JiraAlertMap(GemstoneDB):
    """
    Correlates Jira alert alias to local routing context and Jira alert UUID.

    ``jira_alert_id`` is null after ``trigger_alert`` POST until JSM delivers the Create action.
    """

    __tablename__ = "jira_alert_map"

    bot_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    alias: Mapped[str] = mapped_column(String(128), primary_key=True)
    short_id: Mapped[str] = mapped_column(String(8), nullable=False)
    room_id: Mapped[str] = mapped_column(String, nullable=False)
    jira_alert_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    sender_name: Mapped[str] = mapped_column(String(256), nullable=False, default="Someone")

    __table_args__ = (
        Index("ix_jira_alert_map_bot_short_id", "bot_key", "short_id"),
    )
# -- End Class JiraAlertMap
