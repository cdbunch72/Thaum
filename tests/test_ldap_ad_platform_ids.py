# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_ldap_ad_platform_ids.py
from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace

from lookup.plugins.ldap_ad import (
    merge_platform_ids_from_ldap,
    parse_platform_ids_format,
    parse_platform_ids_from_ldap_entry,
)


class ParsePlatformIdsFormatTest(unittest.TestCase):
    def test_json(self) -> None:
        self.assertEqual(parse_platform_ids_format("json"), ("json", ":"))

    def test_delimited_default_colon(self) -> None:
        self.assertEqual(parse_platform_ids_format("multi-value-attr-delimited"), ("delimited", ":"))

    def test_delimited_explicit(self) -> None:
        self.assertEqual(parse_platform_ids_format("multi-value-attr-delimited(/)"), ("delimited", "/"))
        self.assertEqual(parse_platform_ids_format("multi-value-attr-delimited(,)"), ("delimited", ","))

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_platform_ids_format("yaml")
        with self.assertRaises(ValueError):
            parse_platform_ids_format("multi-value-attr-delimited(x)")


class MergePlatformIdsTest(unittest.TestCase):
    def test_extra_wins(self) -> None:
        self.assertEqual(
            merge_platform_ids_from_ldap({"webex": "a", "jira": "old"}, {"jira": "new"}),
            {"webex": "a", "jira": "new"},
        )


class _FakeEntry:
    def __init__(self, attrs: dict) -> None:
        self._attrs = attrs

    def __getitem__(self, key: str):
        return self._attrs[key]


class ParseFromEntryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.log = logging.getLogger("test")

    def test_json_object(self) -> None:
        attr = SimpleNamespace(value='{"jira":"jid","webex":"w"}')
        entry = _FakeEntry({"ext": attr})
        out = parse_platform_ids_from_ldap_entry(
            entry, "ext", "json", ":", self.log
        )
        self.assertEqual(out, {"jira": "jid", "webex": "w"})

    def test_json_invalid_returns_empty(self) -> None:
        attr = SimpleNamespace(value="not json")
        entry = _FakeEntry({"ext": attr})
        out = parse_platform_ids_from_ldap_entry(
            entry, "ext", "json", ":", self.log
        )
        self.assertEqual(out, {})

    def test_delimited_multi_value(self) -> None:
        attr = SimpleNamespace(values=["jira:acc1", "webex:x"])
        entry = _FakeEntry({"ext": attr})
        out = parse_platform_ids_from_ldap_entry(
            entry, "ext", "delimited", ":", self.log
        )
        self.assertEqual(out, {"jira": "acc1", "webex": "x"})

    def test_delimited_first_split_only(self) -> None:
        attr = SimpleNamespace(values=["jira:acc:extra"])
        entry = _FakeEntry({"ext": attr})
        out = parse_platform_ids_from_ldap_entry(
            entry, "ext", "delimited", ":", self.log
        )
        self.assertEqual(out, {"jira": "acc:extra"})
