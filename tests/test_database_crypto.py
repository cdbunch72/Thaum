# tests/test_database_crypto.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import tempfile
import unittest

from gemstone_utils.sqlalchemy.key_storage import GemstoneKeyRecord

from lookup.db_bootstrap import init_lookup_db
from thaum.database_crypto import apply_database_crypto, is_database_crypto_ready
from thaum.types import ServerConfig


def _server_with_vault(passphrase: str) -> ServerConfig:
    return ServerConfig(
        base_url="https://test.example.com",
        bot_type="webex",
        thaum_state_dir=tempfile.mkdtemp(prefix="thaum_crypto_test_"),
        database_vault_passphrase=passphrase,
    )


class DatabaseCryptoBootstrapTest(unittest.TestCase):
    def test_apply_database_crypto_creates_key_rows(self) -> None:
        init_lookup_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

        from gemstone_utils.db import get_session

        with get_session() as session:
            r0 = session.get(GemstoneKeyRecord, 0)
            r1 = session.get(GemstoneKeyRecord, 1)
            self.assertIsNotNone(r0)
            self.assertIsNotNone(r1)

        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())
