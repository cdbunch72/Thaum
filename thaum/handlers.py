# thaum/handlers.py
# Copyright 2026 <<Name>>. All rights reserved.
# This source file licensed under the Mozilla Public License 2.0

from jinja2 import Template
from thaum.engine import create_incident_room, acknowledge_incident
from typing import TYPE_CHECKING
import re

if TYPE_CHECKING:
    from bots.base import BaseChatBot,MessageContext
    from thaum.types import ThaumPerson



# Define the template globally (or in a separate file if it gets too long)
USAGE_TEMPLATE = """
help[: summary]
  Creates a new room and adds you and {{ bot.team_description }}
  {%- if bot.send_alerts %} and alerts the on-call person.{% endif %}
  If summary is not provided, you will be prompted. The summary is echoed in the new room
  {%- if bot.send_alerts %} and included in the alert.{% endif %}
{% if bot.high_pri_on %}
emergency[: summary]
  Just like help, but sends a higher priority alert. {{ bot.emergency_warning_message }}
{% endif %}
{% if bot.send_alerts %}
alert[: message]
  Alerts the {{ bot.team_description }} on-call with a message. Does not create a room.
  Produces an alert ID for tracking.
ack alert_id
  Acknowledges an alert and assigns ownership to you.
{% endif %}
implode
  Deletes the current room if {{ bot.name }} created it.
usage|commands|?
  Prints this message.
"""



def bind_thaum_handlers(bot: 'BaseChatBot') -> None:
    """Connects Bot events to Engine business logic."""
    
    # Handles the Help or conditionally the emergency command
    def handle_help_emergency(bot: 'BaseChatBot', message: 'MessageContext', match: re.Match):
        cmd, summary = match.group('cmd').lower(), match.group('summary')
        create_incident_room(bot, summary or "...", cmd == "emergency", message.person)
    # -- End Function handle_help_emergency

    # register both commands to the same handler
    bot.hears(r"^(?P<cmd>help)(?:\s*:\s*(?P<summary>.*))?$",priority=10)(handle_help_emergency)
    
    if bot.high_pri_on:
        bot.hears(r"^(?P<cmd>emergency)(?:\s*:\s*(?P<summary>.*))?$",priority=10)(handle_help_emergency)

    # conditionally register the alert and ack commands
    if bot.send_alerts:
        @bot.hears(r"^alert(?:\s*:\s*(?P<msg>.*))",priority=10)
        def handle_alert(bot: 'BaseChatBot', ctx: 'MessageContext', match: re.Match):
            msg=match.group('msg')
            bot.alert_plugin.trigger_alert(msg,ctx.room_id,ctx.person)
    
        @bot.hears(r"^ack\s+(?P<alert_id>[A-Z2-9]{4}).*$",priority=10)
        def handle_ack(bot: 'BaseChatBot', ctx: 'MessageContext', match: re.Match):
            acknowledge_incident(bot, match.group('alert_id'), ctx.person)
    # -- End if send_alerts
    
    @bot.hears(r"^\s*(implode).*$", priority=80)
    def handle_implode(bot: 'BaseChatBot', ctx: 'MessageContext', match: re.Match):
        bot.delete_room(ctx.room_id,ctx.person)
    
    @bot.hears(r"^\s*(usage|commands|\?).*",priority=90)
    def handle_usage(bot, ctx, match):
        # Render with bot as the context object
        rendered = Template(USAGE_TEMPLATE).render(bot=bot)
        bot.say(ctx.room_id, rendered, markdown=True)
    
    @bot.hears(r"^(?P<cmd>\S+)\s+.*$",priority=99)
    def handle_unknown(bot: 'BaseChatBot', ctx: 'MessageContext', match: re.Match):
        bot.say(ctx.room_id,f"Unknown command {match.group('cmd')}. Please use @{bot.name} usage to see a list of commands")

    
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