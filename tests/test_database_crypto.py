# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_database_crypto.py
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from gemstone_utils.db import get_session
from gemstone_utils.encrypted_fields import parse_encrypted_field
from gemstone_utils.sqlalchemy.key_storage import GemstoneKeyKdf, GemstoneKeyRecord
from sqlalchemy import func, select, text

from thaum.db_bootstrap import init_app_db
from thaum.bot_webhook_state import ensure_bot_webhook_hmac_secret
from thaum.database_crypto import (
    apply_database_crypto,
    is_database_crypto_ready,
    progressive_reencrypt_encrypted_strings_if_needed,
    rotate_data_encryption_key_if_due,
)
from thaum.types import ServerConfig, ServerDatabaseConfig


def _server_with_vault(passphrase: str) -> ServerConfig:
    return ServerConfig(
        base_url="https://test.example.com",
        bot_type="webex",
        database=ServerDatabaseConfig(database_vault_passphrase=passphrase),
    )


class DatabaseCryptoBootstrapTest(unittest.TestCase):
    def test_apply_database_crypto_creates_key_rows(self) -> None:
        init_app_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

        with get_session() as session:
            n_kdf = session.scalar(select(func.count()).select_from(GemstoneKeyKdf))
            n_dek = session.scalar(
                select(func.count()).select_from(GemstoneKeyRecord).where(
                    GemstoneKeyRecord.is_active.is_(True)
                )
            )
            self.assertEqual(n_kdf, 1)
            self.assertEqual(n_dek, 1)
            kdf = session.scalars(select(GemstoneKeyKdf)).first()
            self.assertIsNotNone(kdf)
            assert kdf is not None
            self.assertIsNotNone(kdf.canary_wrapped)

        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

    def test_dek_rotation_then_progressive_catchup(self) -> None:
        init_app_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        srv.database.data_key_rotate_days = 1
        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

        ensure_bot_webhook_hmac_secret("b1")

        kid_before: str
        with get_session() as session:
            r = session.scalars(
                select(GemstoneKeyRecord).where(GemstoneKeyRecord.is_active.is_(True))
            ).first()
            self.assertIsNotNone(r)
            assert r is not None
            kid_before = r.key_id
            r.created_at = datetime.now(timezone.utc) - timedelta(days=2)
            session.commit()

        rotate_data_encryption_key_if_due(srv)

        with get_session() as session:
            raw = session.execute(
                text("SELECT secret_enc FROM bot_webhook_hmac WHERE bot_key = :k"),
                {"k": "b1"},
            ).scalar_one()
            _, kid_wire_before, _, _ = parse_encrypted_field(raw)
            self.assertEqual(kid_wire_before, kid_before)

        progressive_reencrypt_encrypted_strings_if_needed(srv)

        with get_session() as session:
            raw = session.execute(
                text("SELECT secret_enc FROM bot_webhook_hmac WHERE bot_key = :k"),
                {"k": "b1"},
            ).scalar_one()
            _, kid_after, _, _ = parse_encrypted_field(raw)
            r_active = session.scalars(
                select(GemstoneKeyRecord).where(GemstoneKeyRecord.is_active.is_(True))
            ).first()
            self.assertIsNotNone(r_active)
            assert r_active is not None
            self.assertEqual(kid_after, r_active.key_id)
            self.assertNotEqual(kid_after, kid_before)
