# thaum/handlers.py
# Copyright 2026 <<Name>>. All rights reserved.

from thaum.engine import create_incident_room, acknowledge_incident
from typing import TYPE_CHECKING
import re

if TYPE_CHECKING:
    from bots.base import BaseBot,MessageContext

def bind_thaum_handlers(bot) -> None:
    """Connects Bot events to Engine business logic."""

    @bot.hears(r"^(help|emergency)(?:\s*:\s*(.*))?$")
    def handle_help_emergency(bot: 'BaseBot', message: 'MessageContext', match: re.Match):
        cmd, summary = match.group(1).lower(), match.group(2)
        if cmd == "emergency" and not bot.emergency_enabled:
            bot.say(message.roomId, "⚠️ 'emergency' command is disabled.")
            return
        create_incident_room(bot, summary or "...", cmd == "emergency", message.personId)
    # -- End Function handle_help_emergency

    @bot.hears(r"^alert(?:\s*:\s*(?P<msg>.*))")
    def handle_alert(bot: 'BaseBot', message: 'MessageContext', match: re.Match):
        msg=match.group('msg')
        bot.alert_plugin.trigger_alert()
    
    @bot.hears(r"^ack\s+(.+)$")
    def handle_ack(bot: 'BaseBot', message: 'MessageContext', match: re.Match):
        if bot.incident_room_only:
            bot.say(message.roomId, "❌ 'ack' disabled for this bot.")
            return
        acknowledge_incident(bot, match.group(1), message.personId)
    # -- End Function handle_ack

    @bot.on_action
    def handle_actions(bot, action):
        """Processes Adaptive Card submissions."""
        # 1. Input Validation
        action_type = action.inputs.get("action")
        if action_type != "submit_incident":
            return

        # 2. Extract and Validate inputs with defaults
        summary = action.inputs.get("summary", "No summary provided")
        is_emergency = action.inputs.get("is_emergency") == "true"
        
        # 3. Resolve Identity via Driver-HAL
        # This keeps the Engine purely based on ThaumPerson objects
        speaker = bot.get_person(action.personId)
        
        # 4. Engine Call
        create_incident_room(bot, summary, is_emergency, speaker)
    # -- End Function handle_actions
# -- End Function bind_thaum_handlers