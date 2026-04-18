# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_lookup_atlassian.py
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from thaum.types import ThaumTeam
from types import SimpleNamespace

from lookup.plugins.atlassian import AtlassianLookupPlugin


class AtlassianLookupPluginUnitTest(unittest.TestCase):
    def test_fetch_team_members_parses_results(self) -> None:
        plugin = AtlassianLookupPlugin(
            site_url="https://site.example.net",
            cloud_id="cid",
            org_id="oid",
            user="u@example.net",
            api_token="tok",
            default_team_ttl_seconds=3600,
        )
        stub_bot = SimpleNamespace(lookup_plugin=None, log=plugin.logger)
        team = ThaumTeam(bot=stub_bot, team_name="T", lookup_id="tid-1")

        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {
            "results": [{"accountId": "acc-1"}, {"accountId": "acc-2"}],
            "pageInfo": {"hasNextPage": False},
        }
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.url = "https://example/post"

        calls = {"n": 0}

        def get_side_effect(*_a: object, **_k: object) -> MagicMock:
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.url = "https://example/get"
            n = calls["n"]
            calls["n"] = n + 1
            r.json.return_value = {
                "emailAddress": ["a@x.com", "b@x.com"][n],
                "displayName": f"User {n}",
            }
            return r

        mock_get = MagicMock(side_effect=get_side_effect)

        with patch("lookup.plugins.atlassian.requests.post", mock_post):
            with patch("lookup.plugins.atlassian.requests.get", mock_get):
                members = plugin.fetch_team_members(team)

        self.assertEqual(len(members), 2)
        self.assertEqual({m.email for m in members}, {"a@x.com", "b@x.com"})

    def test_get_person_by_email_cache_hit_skips_http(self) -> None:
        plugin = AtlassianLookupPlugin(
            site_url="https://site.example.net",
            cloud_id="cid",
            org_id="oid",
            user="u@example.net",
            api_token="tok",
            default_team_ttl_seconds=3600,
        )
        cached = MagicMock()
        cached.platform_ids = {"jira": "acc-cached"}

        with patch.object(
            AtlassianLookupPlugin,
            "_get_cached_person_by_email",
            return_value=cached,
        ) as mock_cached:
            with patch("lookup.plugins.atlassian.requests.get") as mock_get:
                out = plugin.get_person_by_email("any@example.com")

        self.assertIs(out, cached)
        mock_cached.assert_called_once()
        mock_get.assert_not_called()

    def test_get_person_by_email_jira_search_merges(self) -> None:
        plugin = AtlassianLookupPlugin(
            site_url="https://site.example.net",
            cloud_id="cid",
            org_id="oid",
            user="u@example.net",
            api_token="tok",
            default_team_ttl_seconds=3600,
        )

        with patch.object(AtlassianLookupPlugin, "_get_cached_person_by_email", return_value=None):
            mock_get = MagicMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = [
                {
                    "accountId": "acc-99",
                    "emailAddress": "u@example.com",
                    "displayName": "User",
                }
            ]
            mock_resp.raise_for_status = MagicMock()
            mock_resp.url = "https://site.example.net/rest/api/3/user/search"
            mock_get.return_value = mock_resp

            merged = MagicMock()
            merged.platform_ids = {"jira": "acc-99"}

            with patch("lookup.plugins.atlassian.requests.get", mock_get):
                with patch.object(AtlassianLookupPlugin, "merge_person", return_value=merged) as mock_merge:
                    out = plugin.get_person_by_email("u@example.com")

        self.assertIs(out, merged)
        mock_merge.assert_called_once()
        frag = mock_merge.call_args[0][0]
        self.assertEqual(frag.email, "u@example.com")
        self.assertEqual(frag.platform_ids.get("jira"), "acc-99")
