# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_handlers_usage_ack.py
"""Tests for usage text and supports_acknowledge in thaum.handlers."""
import unittest
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

from jinja2 import Template

from thaum.handlers import USAGE_TEMPLATE, bind_thaum_handlers
from thaum.types import ThaumPerson


class _StubAlertPlugin:
    supports_acknowledge = True


class _StubAlertPluginNoAck:
    supports_acknowledge = False


class _AlertPluginWithId:
    supports_acknowledge = False

    def trigger_alert(self, _msg, _room_id, _person):
        return ("ZXCV", "jira-id")


class _AlertPluginNoId:
    supports_acknowledge = True

    def trigger_alert(self, _msg, _room_id, _person):
        return ("", None)


class UsageTemplateAckTest(unittest.TestCase):
    def test_usage_includes_ack_when_supports_acknowledge(self) -> None:
        bot = MagicMock()
        bot.send_alerts = True
        bot.team_description = "SRE"
        bot.high_pri_on = False
        bot.name = "ThaumBot"
        bot.emergency_warning_message = ""
        rendered = Template(USAGE_TEMPLATE).render(bot=bot, supports_acknowledge=True)
        self.assertIn("ack alert_id", rendered)
        self.assertIn("Produces an alert ID for tracking", rendered)

    def test_usage_omits_ack_when_not_supported(self) -> None:
        bot = MagicMock()
        bot.send_alerts = True
        bot.team_description = "SRE"
        bot.high_pri_on = False
        bot.name = "ThaumBot"
        bot.emergency_warning_message = ""
        rendered = Template(USAGE_TEMPLATE).render(bot=bot, supports_acknowledge=False)
        self.assertNotIn("ack alert_id", rendered)
        self.assertNotIn("Produces an alert ID for tracking", rendered)
        self.assertIn("alert[: message]", rendered)


class BindHandlersAckTest(unittest.TestCase):
    def test_ack_handler_registered_only_when_supported(self) -> None:
        bot = MagicMock()
        bot.send_alerts = True
        bot.high_pri_on = False
        bot.alert_plugin = _StubAlertPlugin()
        bot.hears = MagicMock(return_value=lambda f: f)

        bind_thaum_handlers(bot)

        patterns = [c[0][0] for c in bot.hears.call_args_list]
        ack_patterns = [p for p in patterns if "ack" in p and "alert_id" in p]
        self.assertEqual(len(ack_patterns), 1)

    def test_ack_handler_not_registered_when_unsupported(self) -> None:
        bot = MagicMock()
        bot.send_alerts = True
        bot.high_pri_on = False
        bot.alert_plugin = _StubAlertPluginNoAck()
        bot.hears = MagicMock(return_value=lambda f: f)

        bind_thaum_handlers(bot)

        patterns = [c[0][0] for c in bot.hears.call_args_list]
        ack_patterns = [p for p in patterns if "ack" in p and "alert_id" in p]
        self.assertEqual(len(ack_patterns), 0)


class AlertCommandShortIdOutputTest(unittest.TestCase):
    @staticmethod
    def _person() -> ThaumPerson:
        return ThaumPerson(email="x@example.com", display_name="X Person")

    @staticmethod
    def _build_bot(alert_plugin):
        routes = []

        def _hears(pattern, priority=50):
            compiled = re.compile(pattern)

            def _decorator(fn):
                routes.append((compiled, fn))
                return fn

            return _decorator

        return SimpleNamespace(
            send_alerts=True,
            high_pri_on=False,
            alert_plugin=alert_plugin,
            hears=_hears,
            on_action=lambda fn: fn,
            say=MagicMock(),
            delete_room=MagicMock(),
            team_description="SRE",
            name="ThaumBot",
            emergency_warning_message="",
            send_card=MagicMock(),
            get_person=MagicMock(),
            delete_message=MagicMock(),
        ), routes

    def test_alert_command_shows_tracking_id_when_present_even_without_ack_support(self) -> None:
        bot, routes = self._build_bot(_AlertPluginWithId())
        bind_thaum_handlers(bot)
        alert_handler = next(fn for pattern, fn in routes if pattern.pattern.startswith("^alert"))
        ctx = SimpleNamespace(room_id="room-1", person=self._person())
        match = re.search(r"^alert(?:\s*:\s*(?P<msg>.*))", "alert: test issue")
        self.assertIsNotNone(match)
        alert_handler(bot, ctx, match)
        bot.say.assert_called_once_with("room-1", "Alert sent. Tracking ID: **ZXCV**")

    def test_alert_command_falls_back_when_no_short_id(self) -> None:
        bot, routes = self._build_bot(_AlertPluginNoId())
        bind_thaum_handlers(bot)
        alert_handler = next(fn for pattern, fn in routes if pattern.pattern.startswith("^alert"))
        ctx = SimpleNamespace(room_id="room-2", person=self._person())
        match = re.search(r"^alert(?:\s*:\s*(?P<msg>.*))", "alert: test issue")
        self.assertIsNotNone(match)
        alert_handler(bot, ctx, match)
        bot.say.assert_called_once_with("room-2", "Alert sent.")


if __name__ == "__main__":
    unittest.main()
