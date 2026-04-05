# thaum/bot_webhook_state.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from gemstone_utils.db import GemstoneDB, get_session
from gemstone_utils.sqlalchemy.encrypted_type import EncryptedString

if TYPE_CHECKING:
    pass

logger = logging.getLogger("thaum.bot_webhook_state")


class BotWebhookHmac(GemstoneDB):
    """Per-bot shared Webex webhook HMAC secret (encrypted at rest)."""

    __tablename__ = "bot_webhook_hmac"

    bot_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    secret_enc: Mapped[Any] = mapped_column(EncryptedString(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _plaintext_from_secret_field(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "get"):
        return str(value.get())  # LazySecret
    return str(value)


def ensure_bot_webhook_hmac_secret(bot_key: str, *, min_length: int = 16) -> str:
    """
    Return the shared HMAC secret for ``bot_key``, creating a random one if missing.

    Uses insert-or-race so multiple workers can converge on one row.
    """
    for attempt in range(3):
        with get_session() as session:
            row = session.get(BotWebhookHmac, bot_key)
            if row is not None:
                return _plaintext_from_secret_field(row.secret_enc)

        plain = secrets.token_hex(max(16, (min_length + 1) // 2))
        try:
            with get_session() as session:
                with session.begin():
                    session.add(
                        BotWebhookHmac(
                            bot_key=bot_key,
                            secret_enc=plain,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
            return plain
        except IntegrityError:
            logger.debug("bot_webhook_hmac insert race for %r; retrying", bot_key)
            continue

    with get_session() as session:
        row = session.get(BotWebhookHmac, bot_key)
        if row is None:
            raise RuntimeError(f"failed to ensure BotWebhookHmac for {bot_key!r}")
        return _plaintext_from_secret_field(row.secret_enc)


def iter_all_bot_webhook_hmac_rows(session):
    return session.scalars(select(BotWebhookHmac)).all()


def re_encrypt_bot_webhook_hmac_secrets(session, plaintext_by_bot_key: dict[str, str]) -> None:
    """Assign new plaintext secrets under the current EncryptedString write context."""
    now = datetime.now(timezone.utc)
    for bot_key, plain in plaintext_by_bot_key.items():
        row = session.get(BotWebhookHmac, bot_key)
        if row is None:
            session.add(
                BotWebhookHmac(bot_key=bot_key, secret_enc=plain, updated_at=now)
            )
        else:
            row.secret_enc = plain
            row.updated_at = now
