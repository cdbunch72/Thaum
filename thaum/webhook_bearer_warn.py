# thaum/webhook_bearer_warn.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from emerald_utils.db import EmeraldDB


class WebhookBearerWarnState(EmeraldDB):
    """
    Shared throttle for status webhook bearer pre-expiry warnings (SHA-256 of canonical JSON).

    Stores only ``token_fp`` (hex digest), not raw bearer material.
    """

    __tablename__ = "webhook_bearer_warn_state"

    token_fp: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_warn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bot_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
