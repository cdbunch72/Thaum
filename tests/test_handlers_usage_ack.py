# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_handlers_usage_ack.py
"""Tests for usage text and supports_acknowledge in thaum.handlers."""
import unittest
from unittest.mock import MagicMock

from jinja2 import Template

from thaum.handlers import USAGE_TEMPLATE, bind_thaum_handlers


class _StubAlertPlugin:
    supports_acknowledge = True


class _StubAlertPluginNoAck:
    supports_acknowledge = False


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


if __name__ == "__main__":
    unittest.main()
