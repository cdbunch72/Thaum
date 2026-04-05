# thaum/crypto_metadata.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from gemstone_utils.db import GemstoneDB

THAUM_CRYPTO_METADATA_ID = 1


class ThaumCryptoMetadata(GemstoneDB):
    """Singleton row (id=1): active DEK logical id + last rotation timestamp."""

    __tablename__ = "thaum_crypto_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_dek_key_id: Mapped[int] = mapped_column(Integer, nullable=False)
    last_dek_rotated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
