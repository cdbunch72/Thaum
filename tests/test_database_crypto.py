# tests/test_database_crypto.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from gemstone_utils.db import get_session
from gemstone_utils.encrypted_fields import parse_encrypted_field
from gemstone_utils.sqlalchemy.key_storage import GemstoneKeyRecord
from sqlalchemy import text

from lookup.db_bootstrap import init_lookup_db
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
        thaum_state_dir=tempfile.mkdtemp(prefix="thaum_crypto_test_"),
        database=ServerDatabaseConfig(database_vault_passphrase=passphrase),
    )


class DatabaseCryptoBootstrapTest(unittest.TestCase):
    def test_apply_database_crypto_creates_key_rows(self) -> None:
        init_lookup_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

        with get_session() as session:
            r0 = session.get(GemstoneKeyRecord, 0)
            r1 = session.get(GemstoneKeyRecord, 1)
            self.assertIsNotNone(r0)
            self.assertIsNotNone(r1)
            self.assertFalse(r0.is_active)
            self.assertTrue(r1.is_active)

        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

    def test_dek_rotation_then_progressive_catchup(self) -> None:
        init_lookup_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        srv.database.data_key_rotate_days = 1
        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

        ensure_bot_webhook_hmac_secret("b1")

        with get_session() as session:
            r1 = session.get(GemstoneKeyRecord, 1)
            self.assertIsNotNone(r1)
            r1.created_at = datetime.now(timezone.utc) - timedelta(days=2)
            session.commit()

        rotate_data_encryption_key_if_due(srv)

        with get_session() as session:
            raw = session.execute(
                text("SELECT secret_enc FROM bot_webhook_hmac WHERE bot_key = :k"),
                {"k": "b1"},
            ).scalar_one()
            _, kid_before, _, _ = parse_encrypted_field(raw)
            self.assertEqual(kid_before, 1)

        progressive_reencrypt_encrypted_strings_if_needed(srv)

        with get_session() as session:
            raw = session.execute(
                text("SELECT secret_enc FROM bot_webhook_hmac WHERE bot_key = :k"),
                {"k": "b1"},
            ).scalar_one()
            _, kid_after, _, _ = parse_encrypted_field(raw)
            self.assertEqual(kid_after, 2)
