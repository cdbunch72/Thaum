# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/leader_init_status.py
"""Singleton DB row coordinating leader-only bootstrap tasks across workers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from gemstone_utils.db import GemstoneDB

LEADER_INIT_ROW_ID = 1

# Leader holds RUNNING while tasks execute; followers block until DONE or FAILED.
STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"


class LeaderInitStatus(GemstoneDB):
    """
    Single row (``id`` = :data:`LEADER_INIT_ROW_ID`): barrier for ``initialize_bots``.

    Non-leader workers poll until ``state`` is ``done`` or ``failed`` after the leader
    sets ``running`` for the current bootstrap.
    """

    __tablename__ = "schema_leader_init_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    barrier_ticket: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

# -- End Class LeaderInitStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
