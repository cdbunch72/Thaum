# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_health_endpoints.py
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from thaum.db_bootstrap import init_app_db
from log_setup import configure_logging
from thaum.types import LogConfig, LogLevel, ServerAdminConfig, ServerConfig
from web import create_app


def _zero_key_b64u() -> str:
    import base64

    return base64.urlsafe_b64encode(bytes(32)).decode("ascii").rstrip("=")


def _make_server() -> ServerConfig:
    admin = ServerAdminConfig(
        route_id="testrouteid001",
        hmac_secret_b64url=_zero_key_b64u(),
        clock_skew_seconds=600,
        log_state_poll_seconds=0.0,
    )
    return ServerConfig(
        base_url="https://test.example.com",
        bot_type="webex",
        admin=admin,
    )


class HealthEndpointsTest(unittest.TestCase):
    def setUp(self) -> None:
        init_app_db("sqlite:///:memory:")
        self._server = _make_server()
        configure_logging(LogConfig(level=LogLevel.INFO), self._server)
        self.app = create_app(
            {"server": self._server, "log": LogConfig(level=LogLevel.INFO), "bots": {}},
            run_leader_loop=False,
        )
        self.client = self.app.test_client()

    def test_health_returns_ok(self) -> None:
        rv = self.client.get("/health")
        self.assertEqual(rv.status_code, 200)
        data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data.get("status"), "ok")

    def test_ready_returns_ok_when_db_available(self) -> None:
        rv = self.client.get("/ready")
        self.assertEqual(rv.status_code, 200)
        data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data.get("status"), "ok")

    @patch("web.get_session")
    def test_ready_returns_503_when_session_fails(self, mock_get_session: object) -> None:
        mock_get_session.side_effect = RuntimeError("db down")
        rv = self.client.get("/ready")
        self.assertEqual(rv.status_code, 503)
        data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data.get("status"), "unavailable")
        self.assertEqual(data.get("reason"), "database")
