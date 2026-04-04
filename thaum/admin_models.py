# thaum/admin_models.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from gemstone_utils.db import GemstoneDB

ADMIN_LOG_LEVEL_STATE_ID = 1


class AdminLogNonce(GemstoneDB):
    """Single-use nonces for signed POST /…/log-level (replay protection)."""

    __tablename__ = "admin_log_nonce"

    nonce: Mapped[str] = mapped_column(String(32), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminLogLevelState(GemstoneDB):
    """Singleton row (id=1): authoritative runtime log level from admin API."""

    __tablename__ = "admin_log_level_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
