# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/webhook_bearer_warn.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from gemstone_utils.db import GemstoneDB


class WebhookBearerWarnState(GemstoneDB):
    """
    Shared throttle for status webhook bearer pre-expiry warnings (SHA-256 of canonical JSON).

    Stores only ``token_fp`` (hex digest), not raw bearer material.
    """

    __tablename__ = "webhook_bearer_warn_state"

    token_fp: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_warn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bot_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
