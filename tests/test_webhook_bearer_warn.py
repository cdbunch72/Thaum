# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_webhook_bearer_warn.py
from __future__ import annotations

import base64
import logging
import time
import unittest
from datetime import timedelta
from unittest.mock import patch

from gemstone_utils.db import get_session

from alerts.webhook_bearer import (
    canonical_alert_bearer_bytes,
    normalize_expected_secret_to_canonical_bytes,
    validate_webhook_bearer,
    _warn_cache_key,
)
from thaum.db_bootstrap import init_app_db
from thaum.webhook_bearer_warn import WebhookBearerWarnState


def _b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _make_warn_window_secret() -> tuple[str, str]:
    """Return (expected_secret_text, Authorization header value) inside pre-expiry warn window."""
    now = int(time.time())
    exp = now + 5 * 86400
    payload = {"exp": exp, "iat": now, "key": "k" * 16, "warn": 30}
    canonical = canonical_alert_bearer_bytes(payload)
    secret_text = canonical.decode("utf-8")
    auth = f"Bearer {_b64url_nopad(canonical)}"
    return secret_text, auth


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.warning_messages: list[str] = []
        self.error_messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            self.error_messages.append(record.getMessage())
        elif record.levelno >= logging.WARNING:
            self.warning_messages.append(record.getMessage())


class WebhookBearerWarnThrottleTest(unittest.TestCase):
    def setUp(self) -> None:
        init_app_db("sqlite:///:memory:")
        self._log = logging.getLogger("test.webhook_bearer_warn")
        self._log.setLevel(logging.WARNING)
        self._handler = _ListHandler()
        self._log.handlers.clear()
        self._log.addHandler(self._handler)

    def _warn_count(self) -> int:
        return sum(
            1
            for m in self._handler.warning_messages
            if "pre-expiry window" in m
        )

    def test_db_throttles_second_call_within_interval(self) -> None:
        secret, auth = _make_warn_window_secret()
        self.assertTrue(
            validate_webhook_bearer(
                authorization_header_value=auth,
                expected_secret_text=secret,
                logger=self._log,
                bot_key="bot-a",
            )
        )
        self.assertEqual(self._warn_count(), 1)
        self.assertTrue(
            validate_webhook_bearer(
                authorization_header_value=auth,
                expected_secret_text=secret,
                logger=self._log,
                bot_key="bot-a",
            )
        )
        self.assertEqual(self._warn_count(), 1)

        fp = _warn_cache_key(normalize_expected_secret_to_canonical_bytes(secret))
        with get_session() as session:
            row = session.get(WebhookBearerWarnState, fp)
        self.assertIsNotNone(row)
        self.assertEqual(row.bot_key, "bot-a")

    def test_db_logs_again_after_last_warn_aged(self) -> None:
        secret, auth = _make_warn_window_secret()
        fp = _warn_cache_key(normalize_expected_secret_to_canonical_bytes(secret))

        validate_webhook_bearer(
            authorization_header_value=auth,
            expected_secret_text=secret,
            logger=self._log,
        )
        self.assertEqual(self._warn_count(), 1)

        with get_session() as session:
            with session.begin():
                row = session.get(WebhookBearerWarnState, fp)
                self.assertIsNotNone(row)
                row.last_warn_at = row.last_warn_at - timedelta(hours=25)

        self.assertTrue(
            validate_webhook_bearer(
                authorization_header_value=auth,
                expected_secret_text=secret,
                logger=self._log,
            )
        )
        self.assertEqual(self._warn_count(), 2)

    def test_db_unavailable_logs_warning_error_and_skips_rotation_advisory(self) -> None:
        secret, auth = _make_warn_window_secret()
        with patch("gemstone_utils.db.get_session", side_effect=RuntimeError("no db")):
            self.assertTrue(
                validate_webhook_bearer(
                    authorization_header_value=auth,
                    expected_secret_text=secret,
                    logger=self._log,
                )
            )
        self.assertEqual(self._warn_count(), 0)
        self.assertTrue(
            any("rotation throttle skipped" in m for m in self._handler.warning_messages),
            msg=f"expected throttle skip warning, got {self._handler.warning_messages!r}",
        )
        self.assertTrue(
            any("rotation throttle failed" in m for m in self._handler.error_messages),
            msg=f"expected throttle error, got {self._handler.error_messages!r}",
        )


if __name__ == "__main__":
    unittest.main()
