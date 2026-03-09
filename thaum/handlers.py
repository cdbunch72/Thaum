# thaum/handlers.py
# Copyright 2026 <<Name>>. All rights reserved.

from thaum.engine import create_incident_room, acknowledge_incident

def bind_thaum_handlers(bot) -> None:
    """Connects Bot events to Engine business logic."""

    @bot.hears(r"^(help|emergency)(?:\s*:\s*(.*))?$")
    def handle_help_emergency(bot, message, match):
        cmd, summary = match.group(1).lower(), match.group(2)
        if cmd == "emergency" and not bot.emergency_enabled:
            bot.say(message.roomId, "⚠️ 'emergency' command is disabled.")
            return
        create_incident_room(bot, summary or "...", cmd == "emergency", message.personId)
    # -- End Function handle_help_emergency

    @bot.hears(r"^ack\s+(.+)$")
    def handle_ack(bot, message, match):
        if bot.incident_room_only:
            bot.say(message.roomId, "❌ 'ack' disabled for this bot.")
            return
        acknowledge_incident(bot, match.group(1), message.personId)
    # -- End Function handle_ack

    @bot.on_action
    def handle_actions(bot, action):
        if action.inputs.get("action") == "submit_incident":
            create_incident_room(
                bot, 
                action.inputs["summary"], 
                action.inputs.get("is_emergency") == "true", 
                action.personId
            )
    # -- End Function handle_actions
# -- End Function bind_thaum_handlers