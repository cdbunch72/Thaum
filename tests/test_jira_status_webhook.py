# tests/test_jira_status_webhook.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock

from pydantic import SecretStr

from lookup.db_bootstrap import init_lookup_db
from alerts.plugins.jira.mapping_store import (
    apply_create_webhook,
    parse_short_id_from_alias,
    room_id_for_jira_alert,
    upsert_pending_row,
)
from alerts.plugins.jira.status_webhook import handle_jira_status_webhook
from alerts.plugins.jira.config import JiraAlertPluginConfig


class JiraMappingParseTest(unittest.TestCase):
    def test_parse_short_id_from_alias(self) -> None:
        self.assertEqual(parse_short_id_from_alias("THAUM-20260328-ABCD"), "ABCD")
        self.assertEqual(parse_short_id_from_alias("THAUM-20260328-abcD"), "")
        self.assertEqual(parse_short_id_from_alias("other"), "")
        self.assertEqual(parse_short_id_from_alias(None), "")
    # -- End Method test_parse_short_id_from_alias
# -- End Class JiraMappingParseTest


class JiraMappingDbTest(unittest.TestCase):
    def setUp(self) -> None:
        init_lookup_db("sqlite:///:memory:")
    # -- End Method setUp

    def test_pending_then_create_links_jira_id(self) -> None:
        log = logging.getLogger("test.jira")
        upsert_pending_row("WXYZ", "room-1", "bot-a", "THAUM-20260328-WXYZ", log)
        apply_create_webhook(
            jira_alert_id="uuid-one",
            short_id="WXYZ",
            bot_key="bot-a",
            room_id_fallback="",
            alias_fallback="THAUM-20260328-WXYZ",
            logger=log,
        )
        self.assertEqual(room_id_for_jira_alert("uuid-one", "bot-a"), "room-1")
    # -- End Method test_pending_then_create_links_jira_id

    def test_create_without_pending_requires_room(self) -> None:
        log = logging.getLogger("test.jira2")
        apply_create_webhook(
            jira_alert_id="uuid-two",
            short_id="ABCD",
            bot_key="bot-b",
            room_id_fallback="room-x",
            alias_fallback="THAUM-20260328-ABCD",
            logger=log,
        )
        self.assertEqual(room_id_for_jira_alert("uuid-two", "bot-b"), "room-x")
    # -- End Method test_create_without_pending_requires_room
# -- End Class JiraMappingDbTest


class JiraStatusWebhookSayTest(unittest.TestCase):
    def setUp(self) -> None:
        init_lookup_db("sqlite:///:memory:")
        log = logging.getLogger("test.jira3")
        upsert_pending_row("QWER", "space-9", "bk1", "THAUM-20260328-QWER", log)
        apply_create_webhook(
            jira_alert_id="alert-uuid-99",
            short_id="QWER",
            bot_key="bk1",
            room_id_fallback="",
            alias_fallback=None,
            logger=log,
        )
    # -- End Method setUp

    def test_acknowledge_says_to_room(self) -> None:
        bot = MagicMock()
        bot.bot_key = "bk1"
        bot.lookup_plugin = None
        cfg = JiraAlertPluginConfig.model_construct(
            plugin="jira",
            site_url="https://example.atlassian.net",
            cloud_id="c",
            user="u",
            api_token=SecretStr("t"),
            responders=[],
            status_webhook_bearer="",
            send_escalate_msg=False,
        )
        log = logging.getLogger("test.ack")
        handle_jira_status_webhook(
            bot=bot,
            cfg=cfg,
            logger=log,
            payload={
                "action": "Acknowledge",
                "alert": {"alertId": "alert-uuid-99", "username": "responder@example.com"},
            },
        )
        bot.say.assert_called_once()
        args, _kw = bot.say.call_args
        self.assertEqual(args[0], "space-9")
        self.assertIn("acknowledged", args[1].lower())
    # -- End Method test_acknowledge_says_to_room

    def test_escalate_respects_send_flag(self) -> None:
        bot = MagicMock()
        bot.bot_key = "bk1"
        cfg = JiraAlertPluginConfig.model_construct(
            plugin="jira",
            site_url="https://example.atlassian.net",
            cloud_id="c",
            user="u",
            api_token=SecretStr("t"),
            responders=[],
            status_webhook_bearer="",
            send_escalate_msg=False,
        )
        log = logging.getLogger("test.esc")
        handle_jira_status_webhook(
            bot=bot,
            cfg=cfg,
            logger=log,
            payload={"action": "Escalate", "alert": {"alertId": "alert-uuid-99"}},
        )
        bot.say.assert_not_called()
    # -- End Method test_escalate_respects_send_flag
# -- End Class JiraStatusWebhookSayTest


if __name__ == "__main__":
    unittest.main()
