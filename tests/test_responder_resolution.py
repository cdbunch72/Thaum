# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_responder_resolution.py
from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock

from pydantic import SecretStr

from alerts.plugins.jira.config import JiraAlertPluginConfig
from alerts.plugins.jira.payload import responders_list_to_jira_payload
from alerts.plugins.jira.plugin import JiraPlugin
from lookup.base import BaseLookupPlugin
from thaum.db_bootstrap import init_app_db
from thaum.types import RespondersList, ThaumPerson, ThaumTeam


class _LookupTestPlugin(BaseLookupPlugin):
    plugin_name = "test_lookup"

    def fetch_team_members(self, team: ThaumTeam) -> list[ThaumPerson]:
        return list(team._members)


class ResponderResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        init_app_db("sqlite:///:memory:")
        self.lookup = _LookupTestPlugin()
        self.bot = MagicMock()
        self.bot.lookup_plugin = self.lookup
    # -- End Method setUp

    def test_resolve_responder_refs_supports_id_formats(self) -> None:
        self.lookup.cache_team(
            ThaumTeam(bot=self.bot, team_name="DBA", _members=[]),
            bot_plugin_name="jira",
            team_id="team-123",
        )

        responders = self.lookup.resolve_responder_refs(
            self.bot,
            ["id:team:team-123", "id:person:user-456"],
            source_plugin="jira_config",
        )

        self.assertEqual(len(responders.teams), 1)
        self.assertEqual(responders.teams[0].team_name, "DBA")
        self.assertEqual(responders.teams[0].alert_id, "team-123")
        self.assertEqual(len(responders.people), 1)
        self.assertEqual(responders.people[0].platform_ids.get("jira"), "user-456")
    # -- End Method test_resolve_responder_refs_supports_id_formats

    def test_resolve_responder_refs_supports_team_names_with_spaces(self) -> None:
        self.lookup.cache_team(ThaumTeam(bot=self.bot, team_name="DBA Team", _members=[]))
        responders = self.lookup.resolve_responder_refs(self.bot, ["team:DBA Team"])
        self.assertEqual(len(responders.teams), 1)
        self.assertEqual(responders.teams[0].team_name, "DBA Team")
    # -- End Method test_resolve_responder_refs_supports_team_names_with_spaces


class JiraResponderSourceTest(unittest.TestCase):
    def _make_plugin(self, responders: list[str]) -> JiraPlugin:
        cfg = JiraAlertPluginConfig.model_construct(
            plugin="jira",
            site_url="https://example.atlassian.net",
            cloud_id="cloud-id",
            user="user@example.com",
            api_token=SecretStr("token"),
            responders=responders,
            status_webhook_bearer="",
            send_escalate_msg=False,
        )
        plugin = JiraPlugin(cfg)
        plugin._refresh_team_cache = lambda: None
        bot = MagicMock()
        bot.lookup_plugin = MagicMock()
        bot.responders = RespondersList(
            people=[ThaumPerson(email="bot@example.com")],
            teams=[ThaumTeam(bot=bot, team_name="BotTeam", alert_id="team-bot")],
        )
        plugin.attach_bot(bot)
        return plugin

    def test_jira_config_responders_are_authoritative(self) -> None:
        plugin = self._make_plugin(["id:person:user-111"])
        plugin.bot.lookup_plugin.resolve_responder_refs.return_value = RespondersList(
            people=[ThaumPerson(email="jira-account-id:user-111", platform_ids={"jira": "user-111"})],
            teams=[],
        )

        responders = plugin._resolve_alert_responders()

        self.assertEqual(len(responders.people), 1)
        self.assertEqual(responders.people[0].platform_ids.get("jira"), "user-111")
        self.assertTrue(plugin.bot.lookup_plugin.resolve_responder_refs.called)
    # -- End Method test_jira_config_responders_are_authoritative

    def test_empty_jira_responders_fall_back_to_bot_responders(self) -> None:
        plugin = self._make_plugin([])

        responders = plugin._resolve_alert_responders()

        self.assertEqual(len(responders.people), 1)
        self.assertEqual(responders.people[0].email, "bot@example.com")
        self.assertEqual(len(responders.teams), 1)
        self.assertEqual(responders.teams[0].team_name, "BotTeam")
    # -- End Method test_empty_jira_responders_fall_back_to_bot_responders


class JiraResponderPayloadTest(unittest.TestCase):
    def test_payload_prefers_jira_platform_id_for_person(self) -> None:
        responders = RespondersList(
            people=[ThaumPerson(email="placeholder@example.com", platform_ids={"jira": "acct-42"})],
            teams=[],
        )
        resolver = MagicMock(return_value=None)

        payload = responders_list_to_jira_payload(responders, resolver, logging.getLogger("test.jira.payload"))

        self.assertEqual(payload, [{"type": "user", "id": "acct-42"}])
        resolver.assert_not_called()
    # -- End Method test_payload_prefers_jira_platform_id_for_person


if __name__ == "__main__":
    unittest.main()
