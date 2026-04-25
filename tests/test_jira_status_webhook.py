# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_jira_status_webhook.py
from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock

from pydantic import SecretStr

from thaum.db_bootstrap import init_app_db
from alerts.plugins.jira.mapping_store import (
    apply_create_webhook,
    parse_short_id_from_alias,
    room_id_for_jira_alert,
    upsert_pending_row,
)
from thaum.types import AlertPriority, ThaumPerson

from alerts.plugins.jira.payload import (
    build_sender_extra_properties,
    build_trigger_alert_body,
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
        init_app_db("sqlite:///:memory:")
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


class JiraPayloadTest(unittest.TestCase):
    def test_build_sender_extra_properties(self) -> None:
        p = ThaumPerson(
            email="a@example.com",
            display_name="Alice",
            platform_ids={"webex": "webex-person-1"},
        )
        d = build_sender_extra_properties(p, "webex")
        self.assertEqual(d[0], "Alice")
        self.assertEqual(d[1], "webex-person-1")

        bare = ThaumPerson(email="b@example.com", platform_ids={})
        d2 = build_sender_extra_properties(bare, "webex")
        self.assertEqual(d2[0], "Someone")
        self.assertEqual(d2[1], "")
    # -- End Method test_build_sender_extra_properties

    def test_build_trigger_alert_body_includes_string_sender(self) -> None:
        sender = ThaumPerson(
            email="r@example.com",
            display_name="Requester",
            platform_ids={"webex": "pid-r"},
        )
        body = build_trigger_alert_body(
            summary="Something broke",
            bot_name="ThaumBot",
            room_id="room-1",
            sender=sender,
            priority=AlertPriority.NORMAL,
            priority_normal="P3",
            priority_high="P2",
            short_id="ABCD",
            responders_payload=[],
            bot_key="bk",
            plugin_name="webex",
        )
        ep = body["extraProperties"]
        self.assertEqual(ep["sender"], "Requester")
        self.assertEqual(ep["sender_bot_person_id"], "pid-r")
    # -- End Method test_build_trigger_alert_body_includes_string_sender
# -- End Class JiraPayloadTest


class JiraStatusWebhookSayTest(unittest.TestCase):
    def setUp(self) -> None:
        init_app_db("sqlite:///:memory:")
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
        bot.team_description = "Platform"
        bot.lookup_plugin = None
        bot.format_mention = MagicMock(side_effect=lambda x: f"@{x}")
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
        args, kwargs = bot.say.call_args
        self.assertEqual(args[0], "space-9")
        self.assertIn("acknowledged", args[1].lower())
        self.assertTrue(kwargs.get("markdown"))
    # -- End Method test_acknowledge_says_to_room

    def test_acknowledge_status_mentions_false_uses_plain_markdown_flag(self) -> None:
        bot = MagicMock()
        bot.bot_key = "bk1"
        bot.team_description = "Platform"
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
            status_mentions=False,
        )
        log = logging.getLogger("test.ack2")
        handle_jira_status_webhook(
            bot=bot,
            cfg=cfg,
            logger=log,
            payload={
                "action": "Acknowledge",
                "alert": {
                    "alertId": "alert-uuid-99",
                    "username": "responder@example.com",
                    "extraProperties": {
                        "sender": {"name": "Sam", "bot_person_id": "p1"},
                    },
                },
            },
        )
        _args, kwargs = bot.say.call_args
        self.assertFalse(kwargs.get("markdown"))
    # -- End Method test_acknowledge_status_mentions_false_uses_plain_markdown_flag

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
