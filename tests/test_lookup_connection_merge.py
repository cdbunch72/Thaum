# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_lookup_connection_merge.py
from __future__ import annotations

import unittest

from lookup.factory import merge_lookup_connection_profile


class LookupConnectionMergeTest(unittest.TestCase):
    def test_merge_connection_ref_overrides_connection_fields(self) -> None:
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
        merged = merge_lookup_connection_profile(
            full,
            {
                "connection_ref": "main",
                "default_team_ttl_seconds": 100,
                "org_id": "org-override",
            },
        )
        self.assertNotIn("connection_ref", merged)
        self.assertEqual(merged.get("default_team_ttl_seconds"), 100)
        self.assertEqual(merged.get("site_url"), "https://conn.example.net")
        self.assertEqual(merged.get("cloud_id"), "cloud-from-conn")
        self.assertEqual(merged.get("org_id"), "org-override")
        self.assertEqual(merged.get("user"), "u@example.com")
        self.assertEqual(merged.get("api_token"), "secret-from-conn")

    def test_no_connection_ref_unchanged(self) -> None:
        m = {"default_team_ttl_seconds": 1, "site_url": "https://x.net"}
        self.assertEqual(merge_lookup_connection_profile({}, m), m)
