# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_alert_connection_merge.py
from __future__ import annotations

import unittest

from connections.merge import merge_connection_profile


class AlertConnectionMergeTest(unittest.TestCase):
    """Alert bootstrap uses merge_connection_profile for [bots.*.alert] (data-driven via connection_ref)."""

    def test_merge_connection_ref_fills_jira_like_keys(self) -> None:
        full = {
            "connections": {
                "main": {
                    "plugin": "atlassian",
                    "site_url": "https://conn.example.net",
                    "cloud_id": "cloud-from-conn",
                    "org_id": "org-from-conn",
                    "user": "u@example.com",
                    "api_token": "secret-from-conn",
                }
            }
        }
        merged = merge_connection_profile(
            full,
            {
                "connection_ref": "main",
                "status_webhook_bearer": "b",
                "responders": [],
            },
        )
        self.assertNotIn("connection_ref", merged)
        self.assertEqual(merged.get("org_id"), "org-from-conn")
        self.assertEqual(merged.get("site_url"), "https://conn.example.net")
        self.assertEqual(merged.get("cloud_id"), "cloud-from-conn")
        self.assertEqual(merged.get("user"), "u@example.com")
        self.assertEqual(merged.get("api_token"), "secret-from-conn")
        self.assertEqual(merged.get("status_webhook_bearer"), "b")

    def test_consumer_overrides_connection(self) -> None:
        full = {
            "connections": {
                "main": {
                    "plugin": "atlassian",
                    "site_url": "https://a.net",
                    "cloud_id": "c1",
                    "org_id": "o1",
                    "user": "a@a.com",
                    "api_token": "t1",
                }
            }
        }
        merged = merge_connection_profile(
            full,
            {
                "connection_ref": "main",
                "user": "override@example.com",
                "responders": ["team:X"],
                "status_webhook_bearer": "",
            },
        )
        self.assertEqual(merged.get("user"), "override@example.com")
        self.assertEqual(merged.get("org_id"), "o1")

    def test_no_connection_ref_unchanged(self) -> None:
        m = {"site_url": "https://x.net", "status_webhook_bearer": ""}
        self.assertEqual(merge_connection_profile({}, m), m)
