# tests/test_admin_log_level.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import base64
import json
import logging
import unittest
from datetime import datetime, timezone

from lookup.db_bootstrap import init_lookup_db
from log_setup import apply_runtime_log_level_from_db, configure_logging, set_runtime_root_log_level
from thaum.admin_log_level import (
    admin_hmac_secret_bytes,
    build_canonical_message,
    verify_signature,
)
from thaum.admin_models import ADMIN_LOG_LEVEL_STATE_ID, AdminLogLevelState
from thaum.types import LogConfig, LogLevel, ServerConfig
from web import create_app


def _zero_key_b64u() -> str:
    return base64.urlsafe_b64encode(bytes(32)).decode("ascii").rstrip("=")


def _make_server(**kwargs: object) -> ServerConfig:
    base = dict(
        base_url="https://test.example.com",
        bot_type="webex",
        log_admin_route_id="testrouteid001",
        log_admin_hmac_secret_b64url=_zero_key_b64u(),
        log_admin_clock_skew_seconds=600,
        log_admin_state_poll_seconds=0.0,
    )
    base.update(kwargs)
    return ServerConfig(**base)


class AdminLogGoldenVectorTest(unittest.TestCase):
    def test_hmac_matches_documented_vector(self) -> None:
        key = admin_hmac_secret_bytes(_make_server())
        assert key is not None
        msg = build_canonical_message(
            route_id="testrouteid001",
            epoch_seconds=1700000000,
            nonce_hex="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            loglevel_normalized="DEBUG",
        )
        self.assertTrue(
            verify_signature(key, msg, "HS256.yvQxOMFbrgE2e8uqSHAJctxQNClKvdQ9qY62JJ6GqPY")
        )


class AdminLogEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        init_lookup_db("sqlite:///:memory:")
        self._server = _make_server()
        configure_logging(LogConfig(level=LogLevel.INFO), self._server)
        set_runtime_root_log_level(None)
        self.app = create_app({"server": self._server, "log": LogConfig(level=LogLevel.INFO), "bots": {}})
        self.client = self.app.test_client()

    def _sign(
        self,
        *,
        route_id: str,
        epoch: int,
        nonce: str,
        loglevel: str,
    ) -> tuple[dict[str, str], str]:
        key = admin_hmac_secret_bytes(self._server)
        assert key is not None
        norm = loglevel.strip().upper()
        canon = "DEFAULT" if norm == "DEFAULT" else norm
        msg = build_canonical_message(
            route_id=route_id,
            epoch_seconds=epoch,
            nonce_hex=nonce,
            loglevel_normalized=canon,
        )
        import hashlib
        import hmac

        mac = hmac.new(key, msg, hashlib.sha256).digest()
        sig = "HS256." + base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")
        ts = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        headers = {
            "X-Thaum-Timestamp": ts,
            "X-Thaum-Nonce": nonce,
            "X-Thaum-Signature": sig,
            "Content-Type": "application/json",
        }
        body = json.dumps({"loglevel": loglevel, "v": 1})
        return headers, body

    def test_post_debug_updates_db_and_logger(self) -> None:
        epoch = int(datetime.now(timezone.utc).timestamp())
        nonce = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        headers, body = self._sign(
            route_id="testrouteid001",
            epoch=epoch,
            nonce=nonce,
            loglevel="DEBUG",
        )
        rv = self.client.post("/testrouteid001/log-level", headers=headers, data=body)
        self.assertEqual(rv.status_code, 200, rv.get_data(as_text=True))
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

        from gemstone_utils.db import get_session

        with get_session() as session:
            row = session.get(AdminLogLevelState, ADMIN_LOG_LEVEL_STATE_ID)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.log_level, "DEBUG")

    def test_nonce_replay_returns_401(self) -> None:
        epoch = int(datetime.now(timezone.utc).timestamp())
        nonce = "cccccccccccccccccccccccccccccccc"
        headers, body = self._sign(
            route_id="testrouteid001",
            epoch=epoch,
            nonce=nonce,
            loglevel="INFO",
        )
        rv1 = self.client.post("/testrouteid001/log-level", headers=headers, data=body)
        self.assertEqual(rv1.status_code, 200)
        rv2 = self.client.post("/testrouteid001/log-level", headers=headers, data=body)
        self.assertEqual(rv2.status_code, 401)

    def test_bad_signature_returns_401(self) -> None:
        epoch = int(datetime.now(timezone.utc).timestamp())
        headers, _ = self._sign(
            route_id="testrouteid001",
            epoch=epoch,
            nonce="dddddddddddddddddddddddddddddddd",
            loglevel="WARNING",
        )
        headers["X-Thaum-Signature"] = "HS256.AAAA"
        body = json.dumps({"loglevel": "WARNING", "v": 1})
        rv = self.client.post("/testrouteid001/log-level", headers=headers, data=body)
        self.assertEqual(rv.status_code, 401)


class AdminLogDbApplyTest(unittest.TestCase):
    def setUp(self) -> None:
        init_lookup_db("sqlite:///:memory:")
        configure_logging(LogConfig(level=LogLevel.INFO), None)

    def test_apply_from_db_row(self) -> None:
        from gemstone_utils.db import get_session

        now = datetime.now(timezone.utc)
        with get_session() as session:
            session.add(
                AdminLogLevelState(
                    id=ADMIN_LOG_LEVEL_STATE_ID,
                    log_level="ERROR",
                    updated_at=now,
                )
            )
        apply_runtime_log_level_from_db()
        self.assertEqual(logging.getLogger().level, logging.ERROR)
