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
    new_pbkdf2_kdf_params,
    set_kdf_params,
    wire_to_keyrecord,
    wire_wrap,
)

from thaum.bot_webhook_state import (
    _plaintext_from_secret_field,
    iter_all_bot_webhook_hmac_rows,
    re_encrypt_bot_webhook_hmac_secrets,
)
from thaum.crypto_metadata import THAUM_CRYPTO_METADATA_ID, ThaumCryptoMetadata
from thaum.types import ServerConfig

logger = logging.getLogger("thaum.database_crypto")

THAUM_KEK_CHECK_PLAINTEXT = b"thaum-v1-kek-check"
THAUM_VAULT_SECRET_NAME = "thaum-database-vault"

_WRAP_KEY_ID = 1
_FIRST_DEK_ID = 1

_crypto_ready = False


def is_database_crypto_ready() -> bool:
    return _crypto_ready


def _resolved_vault_passphrase(server_cfg: ServerConfig) -> Optional[str]:
    p = getattr(server_cfg, "database_vault_passphrase", None)
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


def _insert_initial_keys(session, passphrase: str) -> None:
    kdf_params = new_pbkdf2_kdf_params()
    kek = derive_kek(passphrase, kdf_params)
    canary = make_kek_check_record(kek)
    dek = os.urandom(32)
    w0 = keyrecord_to_wire(canary, _WRAP_KEY_ID)
    w1 = wire_wrap(_WRAP_KEY_ID, kek, dek)
    set_kdf_params(session, _WRAP_KEY_ID, kdf_params)
    session.add(GemstoneKeyRecord(key_id=0, wrapped=w0))
    session.add(GemstoneKeyRecord(key_id=1, wrapped=w1))
    session.add(
        ThaumCryptoMetadata(
            id=THAUM_CRYPTO_METADATA_ID,
            active_dek_key_id=_FIRST_DEK_ID,
            last_dek_rotated_at=datetime.now(timezone.utc),
        )
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

    active_id = _FIRST_DEK_ID
    ctx = None
    for attempt in range(4):
        session = get_session()
        try:
            if session.get(GemstoneKeyKdf, _WRAP_KEY_ID) is None:
                _insert_initial_keys(session, passphrase)
            if session.get(ThaumCryptoMetadata, THAUM_CRYPTO_METADATA_ID) is None:
                session.add(
                    ThaumCryptoMetadata(
                        id=THAUM_CRYPTO_METADATA_ID,
                        active_dek_key_id=_FIRST_DEK_ID,
                        last_dek_rotated_at=None,
                    )
                )
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

            meta = session.get(ThaumCryptoMetadata, THAUM_CRYPTO_METADATA_ID)
            if meta is None:
                raise RuntimeError("thaum_crypto_metadata singleton row missing after bootstrap")
            active_id = meta.active_dek_key_id
            row_active = session.get(GemstoneKeyRecord, active_id)
            if row_active is None:
                raise RuntimeError(f"active DEK gemstone_key_record {active_id} is missing")

            rec = wire_to_keyrecord(active_id, row_active.wrapped)
            ctx = load_keyctx(kek, rec)
            break
        except IntegrityError:
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
    Leader-only: if ``data_key_rotate_days > 0`` and interval elapsed, create a new DEK row
    and re-encrypt :class:`BotWebhookHmac` rows.
    """
    if server_cfg.data_key_rotate_days <= 0:
        return
    passphrase = _resolved_vault_passphrase(server_cfg)
    if not passphrase:
        return
    if not _crypto_ready:
        apply_database_crypto(server_cfg)
        if not _crypto_ready:
            return

    days = int(server_cfg.data_key_rotate_days)
    now = datetime.now(timezone.utc)
    new_id: int
    plaintext_by_key: dict[str, str]
    kek: bytes
    w_new: str

    with get_session() as session:
        meta = session.get(ThaumCryptoMetadata, THAUM_CRYPTO_METADATA_ID)
        if meta is None:
            return
        last = meta.last_dek_rotated_at
        if last is None:
            with session.begin():
                m0 = session.get(ThaumCryptoMetadata, THAUM_CRYPTO_METADATA_ID)
                if m0 is not None:
                    m0.last_dek_rotated_at = now
            return
        if (now - last) < timedelta(days=days):
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
        w_new = wire_wrap(_WRAP_KEY_ID, kek, new_dek)

        plaintext_by_key = {}
        for row in iter_all_bot_webhook_hmac_rows(session):
            plaintext_by_key[row.bot_key] = _plaintext_from_secret_field(row.secret_enc)

        with session.begin():
            session.add(GemstoneKeyRecord(key_id=new_id, wrapped=w_new))
            meta2 = session.get(ThaumCryptoMetadata, THAUM_CRYPTO_METADATA_ID)
            if meta2 is None:
                raise RuntimeError("ThaumCryptoMetadata missing during rotation")
            meta2.active_dek_key_id = new_id
            meta2.last_dek_rotated_at = now

    new_ctx = load_keyctx(kek, wire_to_keyrecord(new_id, w_new))
    EncryptedString.set_current_keyctx(new_ctx)

    with get_session() as session:
        with session.begin():
            re_encrypt_bot_webhook_hmac_secrets(session, plaintext_by_key)

    logger.warning("Rotated database DEK to logical key_id=%s", new_id)
