# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_handlers_card_submit_delete.py
"""Tests that incident card submit triggers deletion of the parent message."""
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from thaum.handlers import bind_thaum_handlers
from thaum.types import ThaumPerson


class _StubBotForActions:
    """Minimal bot surface for bind_thaum_handlers action path."""

    def __init__(self) -> None:
        self._hears_routes: list = []
        self._action_callbacks: list = []
        self.deleted_messages: list[str] = []
        self.send_alerts = False
        self.high_pri_on = False
        self.team_description = "Team"
        self.handle = "StubBot"
        self.emergency_warning_message = ""

    def hears(self, pattern: str, priority: int = 50):
        def decorator(handler):
            self._hears_routes.append((priority, re.compile(pattern, re.I), handler))
            return handler

        return decorator

    def on_action(self, handler):
        self._action_callbacks.append(handler)
        return handler

    def delete_message(self, message_id: str) -> None:
        self.deleted_messages.append(message_id)

    def get_person(self, person_id: str) -> ThaumPerson:
        return ThaumPerson(
            email="user@example.com",
            display_name="User",
            platform_ids={"webex": person_id},
            source_plugin="webex",
        )


class SubmitIncidentDeletesCardTest(unittest.TestCase):
    @patch("thaum.handlers.create_incident_room")
    def test_submit_incident_calls_delete_message_with_message_id(
        self, mock_create_room
    ) -> None:
        mock_create_room.return_value = "room-1"
        bot = _StubBotForActions()
        bind_thaum_handlers(bot)
        self.assertEqual(len(bot._action_callbacks), 1)
        handle_actions = bot._action_callbacks[0]
        action = SimpleNamespace(
            inputs={
                "action": "submit_incident",
                "summary": "hello",
                "is_emergency": "false",
            },
            personId="person-1",
            messageId="message-abc",
        )
        handle_actions(bot, action)
        mock_create_room.assert_called_once()
        self.assertEqual(bot.deleted_messages, ["message-abc"])

    @patch("thaum.handlers.create_incident_room")
    def test_submit_incident_accepts_snake_case_message_id(
        self, mock_create_room
    ) -> None:
        mock_create_room.return_value = "room-1"
        bot = _StubBotForActions()
        bind_thaum_handlers(bot)
        handle_actions = bot._action_callbacks[0]
        action = SimpleNamespace(
            inputs={
                "action": "submit_incident",
                "summary": "x",
                "is_emergency": "false",
            },
            personId="person-1",
            message_id="msg-snake",
        )
        handle_actions(bot, action)
        self.assertEqual(bot.deleted_messages, ["msg-snake"])

    @patch("thaum.handlers.create_incident_room")
    def test_other_action_does_not_delete(self, mock_create_room) -> None:
        bot = _StubBotForActions()
        bind_thaum_handlers(bot)
        handle_actions = bot._action_callbacks[0]
        action = SimpleNamespace(
            inputs={"action": "something_else"},
            personId="person-1",
            messageId="message-xyz",
        )
        handle_actions(bot, action)
        mock_create_room.assert_not_called()
        self.assertEqual(bot.deleted_messages, [])

    @patch("thaum.handlers.create_incident_room")
    def test_no_message_id_skips_delete(self, mock_create_room) -> None:
        mock_create_room.return_value = "room-1"
        bot = _StubBotForActions()
        bind_thaum_handlers(bot)
        handle_actions = bot._action_callbacks[0]
        action = SimpleNamespace(
            inputs={
                "action": "submit_incident",
                "summary": "hello",
                "is_emergency": "false",
            },
            personId="person-1",
        )
        handle_actions(bot, action)
        mock_create_room.assert_called_once()
        self.assertEqual(bot.deleted_messages, [])

    @patch("thaum.handlers.create_incident_room")
    def test_submit_incident_converts_plus_to_spaces(self, mock_create_room) -> None:
        mock_create_room.return_value = "room-1"
        bot = _StubBotForActions()
        bind_thaum_handlers(bot)
        handle_actions = bot._action_callbacks[0]
        action = SimpleNamespace(
            inputs={
                "action": "submit_incident",
                "summary": "need+help+now",
                "is_emergency": "false",
            },
            personId="person-1",
            messageId="message-plus",
        )
        handle_actions(bot, action)
        args = mock_create_room.call_args.args
        self.assertEqual(args[1], "need help now")
        self.assertEqual(bot.deleted_messages, ["message-plus"])


if __name__ == "__main__":
    unittest.main()
