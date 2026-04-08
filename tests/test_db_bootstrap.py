# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_db_bootstrap.py
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from thaum.db_bootstrap import DEFAULT_APP_DB_URL, resolve_app_db_url
from thaum.types import ServerConfig, ServerDatabaseConfig


class ResolveAppDbUrlTest(unittest.TestCase):
    def test_missing_db_url_falls_back_to_default(self) -> None:
        server = ServerConfig(base_url="https://test.example.com", bot_type="webex")
        self.assertEqual(resolve_app_db_url(server), DEFAULT_APP_DB_URL)

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
