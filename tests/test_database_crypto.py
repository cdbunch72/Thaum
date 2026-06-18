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

from thaum import leader_init
from thaum.bot_webhook_state import ensure_bot_webhook_hmac_secret
from thaum.database_crypto import (
    apply_database_crypto,
    ensure_vault_key_rows,
    is_database_crypto_ready,
    progressive_reencrypt_encrypted_strings_if_needed,
    rotate_data_encryption_key_if_due,
    wire_database_crypto,
)
import thaum.database_crypto as database_crypto_module
from thaum.db_bootstrap import init_app_db
from thaum.leader_init import run_registered_init_tasks
from thaum.maintenance_bootstrap import register_builtin_leader_init_tasks
from thaum.types import ServerConfig, ServerDatabaseConfig


def _server_with_vault(passphrase: str) -> ServerConfig:
    return ServerConfig(
        base_url="https://test.example.com",
        bot_type="webex",
        database=ServerDatabaseConfig(database_vault_passphrase=passphrase),
    )


def _bootstrap_vault(srv: ServerConfig) -> None:
    ensure_vault_key_rows(srv)
    wire_database_crypto(srv)


def _minimal_config(srv: ServerConfig) -> dict:
    return {"server": srv, "bots": {}}


def _count_vault_rows() -> tuple[int, int]:
    with get_session() as session:
        n_kdf = session.scalar(select(func.count()).select_from(GemstoneKeyKdf))
        n_dek = session.scalar(
            select(func.count()).select_from(GemstoneKeyRecord).where(
                GemstoneKeyRecord.is_active.is_(True)
            )
        )
    return int(n_kdf or 0), int(n_dek or 0)


class DatabaseCryptoBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        database_crypto_module._crypto_ready = False
        leader_init.reset_for_tests()

    def test_apply_database_crypto_creates_key_rows(self) -> None:
        init_app_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        _bootstrap_vault(srv)
        self.assertTrue(is_database_crypto_ready())

        n_kdf, n_dek = _count_vault_rows()
        self.assertEqual(n_kdf, 1)
        self.assertEqual(n_dek, 1)

        with get_session() as session:
            kdf = session.scalars(select(GemstoneKeyKdf)).first()
            self.assertIsNotNone(kdf)
            assert kdf is not None
            self.assertIsNotNone(kdf.canary_wrapped)

        apply_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

    def test_ensure_vault_key_rows_idempotent(self) -> None:
        init_app_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        ensure_vault_key_rows(srv)
        ensure_vault_key_rows(srv)
        n_kdf, n_dek = _count_vault_rows()
        self.assertEqual(n_kdf, 1)
        self.assertEqual(n_dek, 1)
        wire_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

    def test_leader_init_task_creates_single_kek_slot(self) -> None:
        init_app_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        config = _minimal_config(srv)
        register_builtin_leader_init_tasks(leader_init, server_cfg=srv, config=config)

        run_registered_init_tasks(srv, config)
        run_registered_init_tasks(srv, config)

        n_kdf, n_dek = _count_vault_rows()
        self.assertEqual(n_kdf, 1)
        self.assertEqual(n_dek, 1)

        database_crypto_module._crypto_ready = False
        wire_database_crypto(srv)
        self.assertTrue(is_database_crypto_ready())

    def test_dek_rotation_then_progressive_catchup(self) -> None:
        init_app_db("sqlite:///:memory:")
        srv = _server_with_vault("unit-test-db-vault-passphrase")
        srv.database.data_key_rotate_days = 1
        _bootstrap_vault(srv)
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
