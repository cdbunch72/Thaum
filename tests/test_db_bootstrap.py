# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_db_bootstrap.py
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from thaum.db_bootstrap import default_bundled_db_url, resolve_app_db_url
from thaum.types import ServerConfig, ServerDatabaseConfig


class ResolveAppDbUrlTest(unittest.TestCase):
    def test_explicit_db_url_used(self) -> None:
        server = ServerConfig(
            base_url="https://test.example.com",
            bot_type="webex",
            database=ServerDatabaseConfig(db_url="sqlite:////var/lib/thaum/thaum.db"),
        )
        self.assertEqual(resolve_app_db_url(server), "sqlite:////var/lib/thaum/thaum.db")

    def test_env_secret_db_url_is_resolved(self) -> None:
        with patch.dict(
            os.environ,
            {"THAUM_TEST_DB_URL": "sqlite:////var/lib/thaum/thaum.db"},
            clear=False,
        ):
            server = ServerConfig(
                base_url="https://test.example.com",
                bot_type="webex",
                database=ServerDatabaseConfig(db_url="env:THAUM_TEST_DB_URL"),
            )
        self.assertEqual(resolve_app_db_url(server), "sqlite:////var/lib/thaum/thaum.db")

    def test_missing_db_url_bundled_default(self) -> None:
        with patch.dict(
            os.environ,
            {"THAUM_EXTERNAL_DB": ""},
            clear=True,
        ):
            server = ServerConfig(base_url="https://test.example.com", bot_type="webex")
            self.assertEqual(
                resolve_app_db_url(server),
                default_bundled_db_url(),
            )

    def test_missing_db_url_external_raises(self) -> None:
        with patch.dict(os.environ, {"THAUM_EXTERNAL_DB": "1"}, clear=True):
            server = ServerConfig(base_url="https://test.example.com", bot_type="webex")
            with self.assertRaises(ValueError):
                resolve_app_db_url(server)


class DefaultBundledDbUrlTest(unittest.TestCase):
    def test_peer_url_no_password(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            u = default_bundled_db_url()
        self.assertTrue(u.startswith("postgresql+psycopg://thaum@/thaum"))
        self.assertIn("host=%2Ftmp%2Fpostgres", u)
        rest = u.split("://", 1)[1]
        auth = rest.split("@", 1)[0]
        self.assertNotIn(":", auth)

    def test_custom_user_via_env(self) -> None:
        with patch.dict(os.environ, {"THAUM_PG_USER": "appuser", "THAUM_PG_DATABASE": "appdb"}):
            u = default_bundled_db_url()
        self.assertIn("postgresql+psycopg://appuser@/appdb", u)
