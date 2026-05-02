# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_config_verify.py
from __future__ import annotations

import importlib.util
import textwrap
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import thaum.db_bootstrap  # noqa: F401 — load thaum package before bootstrap (import order)

from bootstrap import validate_config_after_load
from config import load_and_validate
from thaum.db_bootstrap import verify_app_db_connection
from thaum.types import schema_only_validation


MINIMAL_SCHEMA_TOML = textwrap.dedent(
    """\
    [server]
    base_url = "https://test.example.invalid"
    bot_type = "webex_bot"
    lookup_plugin = "null"

    [server.database]
    database_vault_passphrase = "env:THAUM_SCHEMA_CHECK_MISSING_VAULT"

    [bots.testbot]
    handle = "Test Bot"
    token = "env:THAUM_SCHEMA_CHECK_MISSING_TOKEN"
    send_alerts = false
    high_pri_on = false
    alert_type = "null"
    responders = []
    team_description = "Test"
    emergency_warning_message = "none"
    """
)

MINIMAL_TEST_TOML = textwrap.dedent(
    """\
    [server]
    base_url = "https://test.example.invalid"
    bot_type = "webex_bot"
    lookup_plugin = "null"

    [server.database]
    db_url = "sqlite:///:memory:"
    database_vault_passphrase = "unit-test-vault-passphrase-not-for-production-use"

    [bots.testbot]
    handle = "Test Bot"
    token = "unit-test-webex-token-not-real-use-placeholder-only"
    send_alerts = false
    high_pri_on = false
    alert_type = "null"
    responders = []
    team_description = "Test"
    emergency_warning_message = "none"
    """
)


def _load_thaum_config_check_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts/python/thaum_config_check.py"
    spec = importlib.util.spec_from_file_location("thaum_config_check", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SchemaCheckTest(unittest.TestCase):
    def test_schema_check_unresolvable_env_refs_no_sqlalchemy_engine(self) -> None:
        with NamedTemporaryFile(
            mode="w",
            suffix=".toml",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(MINIMAL_SCHEMA_TOML)
            path = tmp.name

        try:
            with patch("sqlalchemy.create_engine") as mock_create_engine:
                with schema_only_validation():
                    config = load_and_validate(path)
                    validate_config_after_load(config)
            mock_create_engine.assert_not_called()
        finally:
            Path(path).unlink(missing_ok=True)


class TestConfigCliTest(unittest.TestCase):
    def test_run_test_config_invokes_db_ping(self) -> None:
        with NamedTemporaryFile(
            mode="w",
            suffix=".toml",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(MINIMAL_TEST_TOML)
            path = tmp.name

        try:
            mod = _load_thaum_config_check_module()
            with patch("thaum.db_bootstrap.verify_app_db_connection") as mock_ping:
                mod.run_test_config(path)
            mock_ping.assert_called_once()
            url = mock_ping.call_args[0][0]
            self.assertEqual(url, "sqlite:///:memory:")
        finally:
            Path(path).unlink(missing_ok=True)


class TestAppDbConnectionTest(unittest.TestCase):
    def test_select_one_sqlite_memory(self) -> None:
        verify_app_db_connection("sqlite:///:memory:")
