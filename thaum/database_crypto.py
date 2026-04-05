# thaum/database_crypto.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from gemstone_utils.db import get_session
from gemstone_utils.key_mgmt import (
    init as key_mgmt_init,
    derive_and_verify_kek,
    derive_kek,
    load_keyctx,
    make_kek_check_record,
)
from gemstone_utils.sqlalchemy.encrypted_type import EncryptedString
from gemstone_utils.sqlalchemy.key_storage import (
    GemstoneKeyKdf,
    GemstoneKeyRecord,
    get_kdf_params,
    keyrecord_to_wire,
    make_keyctx_resolver,
    new_kdf_params,
    put_keyrecord,
    set_kdf_params,
    wire_to_keyrecord,
    wire_wrap,
)

from thaum.bot_webhook_state import re_encrypt_stale_bot_webhook_hmac_batch
from thaum.types import ServerConfig

logger = logging.getLogger("thaum.database_crypto")

THAUM_KEK_CHECK_PLAINTEXT = b"thaum-v1-kek-check"
THAUM_VAULT_SECRET_NAME = "thaum-database-vault"

_WRAP_KEY_ID = 1
_DATA_ALG = "A256GCM"

# Progressive catch-up: rows per leader tick
_ENCRYPTED_FIELD_CATCHUP_BATCH = 50

_crypto_ready = False


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_database_crypto_ready() -> bool:
    return _crypto_ready


def _resolved_vault_passphrase(server_cfg: ServerConfig) -> Optional[str]:
    p = server_cfg.database.database_vault_passphrase
    if p is None:
        return None
    s = str(p).strip()
    return s or None


def requires_database_vault_passphrase(config: Dict[str, Any]) -> bool:
    for row in (config.get("bots") or {}).values():
        if not isinstance(row, dict):
            continue
        vb = row.get("_validated_bot")
        if vb is None:
            continue
        if getattr(vb, "hmac_mode", None) == "shared_db":
            return True
    return False


def active_dek_row(session) -> Optional[GemstoneKeyRecord]:
    rows = list(
        session.scalars(
            select(GemstoneKeyRecord).where(
                GemstoneKeyRecord.key_id >= 1,
                GemstoneKeyRecord.is_active.is_(True),
            )
        ).all()
    )
    if len(rows) > 1:
        raise RuntimeError("multiple active DEK rows in gemstone_key_record")
    return rows[0] if rows else None


def _insert_initial_keys(session, passphrase: str) -> None:
    kdf_params = new_kdf_params()
    kek = derive_kek(passphrase, kdf_params)
    canary = make_kek_check_record(kek)
    dek = os.urandom(32)
    w0 = keyrecord_to_wire(canary, _WRAP_KEY_ID)
    w1 = wire_wrap(_WRAP_KEY_ID, kek, dek, alg=_DATA_ALG)
    set_kdf_params(session, _WRAP_KEY_ID, kdf_params)
    put_keyrecord(
        session,
        key_id=0,
        wrapped=w0,
        data_alg=_DATA_ALG,
        is_active=False,
    )
    put_keyrecord(
        session,
        key_id=1,
        wrapped=w1,
        data_alg=_DATA_ALG,
        is_active=True,
    )


def apply_database_crypto(server_cfg: ServerConfig) -> None:
    """
    Configure key_mgmt, bootstrap GemstoneKey* rows on first run, and wire
    :class:`EncryptedString` for the process.
    """
    global _crypto_ready
    passphrase = _resolved_vault_passphrase(server_cfg)
    if not passphrase:
        _crypto_ready = False
        return

    key_mgmt_init(
        THAUM_VAULT_SECRET_NAME,
        THAUM_KEK_CHECK_PLAINTEXT,
        env_allowed=False,
    )

    active_id: int
    ctx = None
    for attempt in range(4):
        session = get_session()
        try:
            if session.get(GemstoneKeyKdf, _WRAP_KEY_ID) is None:
                _insert_initial_keys(session, passphrase)
            session.commit()

            kdf_params = get_kdf_params(session, _WRAP_KEY_ID)
            kek = derive_kek(passphrase, kdf_params)
            row0 = session.get(GemstoneKeyRecord, 0)
            if row0 is None:
                raise RuntimeError("gemstone_key_record row 0 (KEK canary) is missing")
            derive_and_verify_kek(
                passphrase,
                kdf_params,
                wire_to_keyrecord(0, row0.wrapped),
            )

            row_active = active_dek_row(session)
            if row_active is None:
                raise RuntimeError("no active DEK row (gemstone_key_record is_active)")
            active_id = row_active.key_id

            rec = wire_to_keyrecord(active_id, row_active.wrapped)
            ctx = load_keyctx(kek, rec)
            break
        except (IntegrityError, ValueError):
            session.rollback()
            logger.debug("vault bootstrap race (attempt %s); retrying", attempt + 1)
            if attempt == 3:
                raise
        finally:
            session.close()

    if ctx is None:
        raise RuntimeError("database crypto bootstrap did not produce a KeyContext")

    def load_passphrase_fn() -> str:
        return _resolved_vault_passphrase(server_cfg) or ""

    EncryptedString.set_keyctx_resolver(
        make_keyctx_resolver(load_passphrase=load_passphrase_fn)
    )
    EncryptedString.set_current_keyctx(ctx)
    _crypto_ready = True
    logger.info("Database field encryption initialized (active_dek_key_id=%s)", active_id)


def rotate_data_encryption_key_if_due(server_cfg: ServerConfig) -> None:
    """
    Leader-only: if ``server.database.data_key_rotate_days > 0`` and interval elapsed,
    create a new active DEK row. Stale ciphertext is upgraded by
    :func:`progressive_reencrypt_encrypted_strings_if_needed`.
    """
    if server_cfg.database.data_key_rotate_days <= 0:
        return
    passphrase = _resolved_vault_passphrase(server_cfg)
    if not passphrase:
        return
    if not _crypto_ready:
        apply_database_crypto(server_cfg)
        if not _crypto_ready:
            return

    days = int(server_cfg.database.data_key_rotate_days)
    now = datetime.now(timezone.utc)

    with get_session() as session:
        active = active_dek_row(session)
        if active is None:
            return
        if (now - _as_utc(active.created_at)) < timedelta(days=days):
            return

        kdf_params = get_kdf_params(session, _WRAP_KEY_ID)
        kek = derive_kek(passphrase, kdf_params)
        row0 = session.get(GemstoneKeyRecord, 0)
        if row0 is None:
            return
        derive_and_verify_kek(
            passphrase,
            kdf_params,
            wire_to_keyrecord(0, row0.wrapped),
        )

        mx = session.scalar(
            select(func.max(GemstoneKeyRecord.key_id)).where(GemstoneKeyRecord.key_id >= 1)
        )
        new_id = int(mx or 1) + 1
        new_dek = os.urandom(32)
        w_new = wire_wrap(_WRAP_KEY_ID, kek, new_dek, alg=_DATA_ALG)

        put_keyrecord(
            session,
            key_id=new_id,
            wrapped=w_new,
            data_alg=_DATA_ALG,
            is_active=True,
        )
        session.commit()

    new_ctx = load_keyctx(kek, wire_to_keyrecord(new_id, w_new))
    EncryptedString.set_current_keyctx(new_ctx)
    logger.warning("Rotated database DEK to logical key_id=%s", new_id)


def progressive_reencrypt_encrypted_strings_if_needed(server_cfg: ServerConfig) -> None:
    """
    Leader-only: re-encrypt a batch of :class:`BotWebhookHmac` rows that still
    reference an older DEK key id in the stored wire string.
    """
    if not _crypto_ready:
        apply_database_crypto(server_cfg)
        if not _crypto_ready:
            return
    passphrase = _resolved_vault_passphrase(server_cfg)
    if not passphrase:
        return

    def load_passphrase_fn() -> str:
        return passphrase

    resolver = make_keyctx_resolver(load_passphrase=load_passphrase_fn)

    with get_session() as session:
        active = active_dek_row(session)
        if active is None:
            return
        n = re_encrypt_stale_bot_webhook_hmac_batch(
            session,
            active_dek_key_id=active.key_id,
            resolve_keyctx=resolver,
            batch_limit=_ENCRYPTED_FIELD_CATCHUP_BATCH,
        )

    if n:
        logger.info("Re-encrypted %s bot_webhook_hmac row(s) under active DEK", n)
