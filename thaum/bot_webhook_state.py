# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/bot_webhook_state.py
from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, String, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import flag_modified

from gemstone_utils.db import GemstoneDB, get_session
from gemstone_utils.encrypted_fields import decrypt_string, parse_encrypted_field
from gemstone_utils.sqlalchemy.encrypted_type import EncryptedString
from gemstone_utils.types import KeyContext

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
    if not str(bot_key).strip():
        raise ValueError("bot_key must be non-empty so HMAC secrets are not shared across bots")
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
            flag_modified(row, "secret_enc")
            row.updated_at = now


def re_encrypt_stale_bot_webhook_hmac_batch(
    session,
    *,
    active_dek_key_id: str,
    resolve_keyctx: Callable[[str], KeyContext],
    batch_limit: int = 50,
) -> int:
    """
    Re-assign plaintext for rows whose stored wire still names a non-active DEK key id
    (UUID string segment in the encrypted-field wire format),
    so values are re-encrypted under :meth:`EncryptedString.set_current_keyctx`.

    Reads ciphertext via raw SQL so the embedded key id can be inspected without ORM coercion.
    """
    if batch_limit <= 0:
        return 0
    conn = session.connection()
    rows = conn.execute(
        text("SELECT bot_key, secret_enc FROM bot_webhook_hmac LIMIT :lim"),
        {"lim": batch_limit},
    ).all()
    pending: list[tuple[str, str]] = []
    for bot_key, ciphertext in rows:
        if not ciphertext or not isinstance(ciphertext, str):
            continue
        try:
            _alg, keyid, _params, _blob = parse_encrypted_field(ciphertext)
        except ValueError:
            continue
        if keyid == active_dek_key_id:
            continue
        plain = decrypt_string(ciphertext, resolve_keyctx(keyid))
        if plain is None:
            continue
        pending.append((bot_key, plain))

    if not pending:
        return 0

    updated = 0
    now = datetime.now(timezone.utc)
    for bot_key, plain in pending:
        row = session.get(BotWebhookHmac, bot_key)
        if row is None:
            continue
        row.secret_enc = plain
        # EncryptedString loads as LazySecret; assigning str can look unchanged to the ORM.
        flag_modified(row, "secret_enc")
        row.updated_at = now
        updated += 1
    session.commit()
    return updated
