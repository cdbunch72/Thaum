# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_engine_customer_service_message.py
"""Tests for customer service incident-room message behavior."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from thaum.engine import create_incident_room
from thaum.types import ThaumPerson


class _AlertPluginStub:
    def trigger_alert(self, summary, room_id, speaker, priority):
        return ("A1B2", "alert-id-1")


class CustomerServiceMessageTest(unittest.TestCase):
    def _speaker(self) -> ThaumPerson:
        return ThaumPerson(
            email="user@example.com",
            display_name="Pat User",
            platform_ids={},
            source_plugin="test",
        )

    def _bot(self) -> SimpleNamespace:
        bot = SimpleNamespace()
        bot.team_description = "Helpdesk"
        bot.room_title_template = "{{ requester_name }} - {{ team_description }} {{ date }}"
        bot.responders = SimpleNamespace(get_responders=lambda: [])
        bot.create_room = MagicMock(return_value="room-1")
        bot.add_members = MagicMock()
        bot.say = MagicMock()
        bot.alert_plugin = _AlertPluginStub()
        bot.logger = MagicMock()
        return bot

    def test_default_customer_service_message_is_sent(self) -> None:
        bot = self._bot()
        bot.customer_service_message_template = None
        room_id = create_incident_room(bot, "Need help", self._speaker())
        self.assertEqual(room_id, "room-1")
        first_text = bot.say.call_args_list[0].args[1]
        self.assertIn("Thank you for your patience.", first_text)
        self.assertIn("Helpdesk", first_text)

    def test_empty_customer_service_message_template_skips_message(self) -> None:
        bot = self._bot()
        bot.customer_service_message_template = ""
        room_id = create_incident_room(bot, "Need help", self._speaker())
        self.assertEqual(room_id, "room-1")
        said_texts = [call.args[1] for call in bot.say.call_args_list]
        self.assertNotIn(
            "Thank you for your patience.  The next available person from Helpdesk will be with you shortlly.",
            said_texts,
        )
        self.assertTrue(any(text.startswith("**Summary:**") for text in said_texts))


if __name__ == "__main__":
    unittest.main()
