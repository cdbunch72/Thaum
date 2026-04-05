# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/models.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from gemstone_utils.db import GemstoneDB


class JiraAlertMap(GemstoneDB):
    """
    Correlates Thaum short_id (primary key) with Jira Ops alert UUID once the Create webhook arrives.

    ``jira_alert_id`` is null after ``trigger_alert`` POST until JSM delivers the Create action.
    """

    __tablename__ = "jira_alert_map"

    short_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    room_id: Mapped[str] = mapped_column(String, nullable=False)
    bot_key: Mapped[str] = mapped_column(String, nullable=False)
    alias: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    jira_alert_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
# -- End Class JiraAlertMap
