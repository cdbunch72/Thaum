# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
"""Tests for Webex inbound mention stripping (personId with optional |display)."""
import unittest

from bots.plugins.webex_bot import strip_leading_bot_labels, strip_webex_self_mentions


class StripWebexSelfMentionsTest(unittest.TestCase):
    def test_person_id_with_display_suffix(self) -> None:
        pid = "Y2lzX3Rlc3Q"
        raw = f"<@personId:{pid}|Ask DBA> implode"
        self.assertEqual(strip_webex_self_mentions(raw, pid, ()), "implode")

    def test_person_id_without_display(self) -> None:
        pid = "abc"
        raw = f"<@personId:{pid}> help: fire"
        self.assertEqual(strip_webex_self_mentions(raw, pid, ()), "help: fire")

    def test_person_email_with_display(self) -> None:
        raw = "<@personEmail:bot@example.com|Bot> alert: smoke"
        self.assertEqual(
            strip_webex_self_mentions(raw, "other-id", ("bot@example.com",)),
            "alert: smoke",
        )

    def test_regex_metacharacters_in_id_escaped(self) -> None:
        pid = "a+b"
        raw = f"<@personId:{pid}|X> ok"
        self.assertEqual(strip_webex_self_mentions(raw, pid, ()), "ok")


class StripLeadingBotLabelsTest(unittest.TestCase):
    def test_plain_display_name_before_command(self) -> None:
        self.assertEqual(
            strip_leading_bot_labels("askDBA implode", "askDBA", "Ask DBA", "askdba"),
            "implode",
        )

    def test_case_insensitive_name(self) -> None:
        self.assertEqual(
            strip_leading_bot_labels("ASKDBA usage", "askDBA"),
            "usage",
        )

    def test_chained_with_mention_strip_like_webex_text_field(self) -> None:
        """Simulates message.text where Webex leaves the display name, not markup."""
        pid = "pid1"
        raw = "askDBA commands"
        after_mentions = strip_webex_self_mentions(raw, pid, ())
        self.assertEqual(after_mentions, raw)
        self.assertEqual(
            strip_leading_bot_labels(after_mentions, "askDBA", "AskDBA"),
            "commands",
        )


if __name__ == "__main__":
    unittest.main()
