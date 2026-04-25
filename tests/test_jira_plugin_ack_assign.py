# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from alerts.plugins.jira.config import JiraAlertPluginConfig
from alerts.plugins.jira.mapping_store import apply_create_webhook, upsert_pending_row
from alerts.plugins.jira.plugin import JiraPlugin
from thaum.db_bootstrap import init_app_db
from thaum.types import ThaumPerson


class _OkResponse:
    def raise_for_status(self) -> None:
        return None


class _FailResponse:
    def raise_for_status(self) -> None:
        raise RuntimeError("assign failed")


class JiraPluginAckAssignTest(unittest.TestCase):
    def setUp(self) -> None:
        init_app_db("sqlite:///:memory:")
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
        self.plugin = JiraPlugin(cfg)
        self.plugin.bot = SimpleNamespace(
            bot_key="bk1",
            say=MagicMock(),
            name="ThaumBot",
            plugin_name="webex",
            responders=SimpleNamespace(),
        )

    def test_ack_and_assign_use_alert_id_when_mapped(self) -> None:
        upsert_pending_row("ABCD", "room-1", "bk1", "THAUM-20260425-ABCD", logging.getLogger("t1"))
        apply_create_webhook(
            jira_alert_id="jira-1",
            short_id="ABCD",
            bot_key="bk1",
            room_id_fallback="",
            alias_fallback="THAUM-20260425-ABCD",
            logger=logging.getLogger("t1"),
        )
        person = ThaumPerson(email="a@example.com", display_name="Alice", platform_ids={"jira": "acct-1"})

        with patch("alerts.plugins.jira.plugin.requests.post", return_value=_OkResponse()) as post_mock:
            self.plugin.acknowledge_alert("ABCD", person)

        self.assertEqual(post_mock.call_count, 2)
        first_url = post_mock.call_args_list[0].args[0]
        second_url = post_mock.call_args_list[1].args[0]
        self.assertTrue(first_url.endswith("/v1/alerts/jira-1/acknowledge"))
        self.assertTrue(second_url.endswith("/v1/alerts/jira-1/assign"))
        self.assertEqual(post_mock.call_args_list[1].kwargs["json"], {"accountId": "acct-1"})
        self.plugin.bot.say.assert_not_called()

    def test_ack_uses_alias_fallback_when_alert_id_pending(self) -> None:
        upsert_pending_row("WXYZ", "room-2", "bk1", "THAUM-20260425-WXYZ", logging.getLogger("t2"))
        person = ThaumPerson(email="b@example.com", display_name="Bob", platform_ids={"jira": "acct-2"})

        with patch("alerts.plugins.jira.plugin.requests.post", return_value=_OkResponse()) as post_mock:
            self.plugin.acknowledge_alert("WXYZ", person)

        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(
            post_mock.call_args_list[0].kwargs.get("params"),
            {"identifierType": "alias"},
        )
        self.assertEqual(
            post_mock.call_args_list[1].kwargs.get("params"),
            {"identifierType": "alias"},
        )

    def test_assign_unresolved_logs_and_warns_room(self) -> None:
        upsert_pending_row("QWER", "room-3", "bk1", "THAUM-20260425-QWER", logging.getLogger("t3"))
        apply_create_webhook(
            jira_alert_id="jira-3",
            short_id="QWER",
            bot_key="bk1",
            room_id_fallback="",
            alias_fallback="THAUM-20260425-QWER",
            logger=logging.getLogger("t3"),
        )
        person = ThaumPerson(email="unknown@example.com", display_name="Unknown", platform_ids={})
        self.plugin._resolve_email_to_account_id = MagicMock(return_value=None)

        with patch("alerts.plugins.jira.plugin.requests.post", return_value=_OkResponse()) as post_mock:
            self.plugin.acknowledge_alert("QWER", person)

        self.assertEqual(post_mock.call_count, 1)
        self.plugin.bot.say.assert_called_once()
        msg = self.plugin.bot.say.call_args.args[1]
        self.assertIn("acknowledged", msg.lower())
        self.assertIn("could not assign", msg.lower())

    def test_assign_api_failure_logs_and_warns_room(self) -> None:
        upsert_pending_row("TYUI", "room-4", "bk1", "THAUM-20260425-TYUI", logging.getLogger("t4"))
        apply_create_webhook(
            jira_alert_id="jira-4",
            short_id="TYUI",
            bot_key="bk1",
            room_id_fallback="",
            alias_fallback="THAUM-20260425-TYUI",
            logger=logging.getLogger("t4"),
        )
        person = ThaumPerson(email="c@example.com", display_name="Chris", platform_ids={"jira": "acct-4"})

        with patch(
            "alerts.plugins.jira.plugin.requests.post",
            side_effect=[_OkResponse(), _FailResponse()],
        ) as post_mock:
            self.plugin.acknowledge_alert("TYUI", person)

        self.assertEqual(post_mock.call_count, 2)
        self.plugin.bot.say.assert_called_once()
        self.assertIn("assignment", self.plugin.bot.say.call_args.args[1].lower())


if __name__ == "__main__":
    unittest.main()
