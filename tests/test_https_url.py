# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_https_url.py
from __future__ import annotations

import unittest

from pydantic import ValidationError

from connections.plugins.atlassian import AtlassianConnectionConfig
from lookup.plugins.atlassian import AtlassianLookupPlugin, AtlassianLookupPluginConfig
from thaum.https_url import normalize_https_base_url


class NormalizeHttpsBaseUrlTest(unittest.TestCase):
    def test_https_ok_strips_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_https_base_url("https://site.example.net/"),
            "https://site.example.net",
        )

    def test_http_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_https_base_url("http://site.example.net")
        self.assertIn("https", str(ctx.exception).lower())

    def test_missing_host_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_https_base_url("https://")
        self.assertIn("hostname", str(ctx.exception).lower())

    def test_credentials_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_https_base_url("https://user:pass@site.example.net")
        self.assertIn("password", str(ctx.exception).lower())


class AtlassianSiteUrlValidationTest(unittest.TestCase):
    def test_lookup_config_rejects_http_site_url(self) -> None:
        with self.assertRaises(ValidationError):
            AtlassianLookupPluginConfig(
                site_url="http://site.example.net",
                cloud_id="cid",
                org_id="oid",
                user="u@example.net",
                api_token="tok",
            )

    def test_lookup_plugin_accepts_https_and_normalizes(self) -> None:
        plugin = AtlassianLookupPlugin(
            site_url="https://site.example.net/",
            cloud_id="cid",
            org_id="oid",
            user="u@example.net",
            api_token="tok",
            default_team_ttl_seconds=3600,
        )
        self.assertEqual(plugin._site_url, "https://site.example.net")

    def test_connection_config_rejects_http_when_set(self) -> None:
        with self.assertRaises(ValidationError):
            AtlassianConnectionConfig(site_url="http://site.example.net")

    def test_connection_config_allows_missing_site_url(self) -> None:
        cfg = AtlassianConnectionConfig()
        self.assertIsNone(cfg.site_url)

    def test_connection_config_normalizes_https(self) -> None:
        cfg = AtlassianConnectionConfig(site_url="https://site.example.net/")
        self.assertEqual(cfg.site_url, "https://site.example.net")
