# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/handlers.py
from jinja2 import Template
from thaum.engine import create_incident_room, acknowledge_incident
from typing import TYPE_CHECKING, Any, Dict, List
from thaum.types import ThaumPerson, AlertPriority
import re

if TYPE_CHECKING:
    from bots.base import BaseChatBot, MessageContext


def _incident_prompt_card(
    team_description: str,
    default_high_priority: bool,
    show_priority_toggle: bool,
) -> Dict[str, Any]:
    """Adaptive Card for help/emergency when the user did not supply a summary on the command line."""
    prompt = f"How can {team_description} help you today?"
    body: List[Dict[str, Any]] = [
        {"type": "TextBlock", "text": prompt, "wrap": True},
        {
            "type": "Input.Text",
            "id": "summary",
            "label": "Summary",
            "placeholder": "Briefly describe what you need",
            "isMultiline": True,
            "isRequired": True,
        },
    ]
    if show_priority_toggle:
        body.append(
            {
                "type": "Input.Toggle",
                "id": "is_emergency",
                "title": "High priority (emergency) alert",
                "value": "true" if default_high_priority else "false",
                "valueOn": "true",
                "valueOff": "false",
            }
        )

    submit_data: Dict[str, str] = {"action": "submit_incident"}
    if not show_priority_toggle:
        submit_data["is_emergency"] = "false"

    return {
        "type": "AdaptiveCard",
        "version": "1.2",
        "body": body,
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Submit",
                "data": submit_data,
            }
        ],
    }




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
{%- if supports_acknowledge %}
  Produces an alert ID for tracking.
ack alert_id
  Acknowledges an alert and assigns ownership to you.
{%- endif %}
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
        cmd = match.group("cmd").lower()
        raw = match.group("summary")
        summary = (raw or "").strip()
        priority = AlertPriority.HIGH if cmd == "emergency" else AlertPriority.NORMAL
        if summary:
            create_incident_room(bot, summary, message.person, priority)
        else:
            card = _incident_prompt_card(
                bot.team_description,
                default_high_priority=(cmd == "emergency"),
                show_priority_toggle=bool(bot.high_pri_on),
            )
            bot.send_card(
                message.room_id,
                card,
                fallback_text="Incident request — please fill in the card.",
            )
    # -- End Function handle_help_emergency

    # register both commands to the same handler
    bot.hears(r"^(?P<cmd>help)(?:\s*:\s*(?P<summary>.*))?$",priority=10)(handle_help_emergency)
    
    if bot.high_pri_on:
        bot.hears(r"^(?P<cmd>emergency)(?:\s*:\s*(?P<summary>.*))?$",priority=10)(handle_help_emergency)

    # conditionally register the alert command; ack only when the plugin supports chat ack
    if bot.send_alerts:
        plugin_cls = type(bot.alert_plugin)

        @bot.hears(r"^alert(?:\s*:\s*(?P<msg>.*))",priority=10)
        def handle_alert(bot: 'BaseChatBot', ctx: 'MessageContext', match: re.Match):
            msg = match.group("msg")
            short_id, _alert_id = bot.alert_plugin.trigger_alert(msg, ctx.room_id, ctx.person)
            if plugin_cls.supports_acknowledge:
                bot.say(
                    ctx.room_id,
                    f"Alert sent. Tracking ID: **{short_id}**",
                    markdown=True,
                )
            else:
                bot.say(ctx.room_id, "Alert sent.", markdown=True)

        if plugin_cls.supports_acknowledge:

            @bot.hears(r"^ack\s+(?P<alert_id>[A-Z2-9]{4}).*$", priority=10)
            def handle_ack(bot: 'BaseChatBot', ctx: 'MessageContext', match: re.Match):
                acknowledge_incident(bot, match.group("alert_id"), ctx.person)
    # -- End if send_alerts
    
    @bot.hears(r"^\s*(implode).*$", priority=80)
    def handle_implode(bot: 'BaseChatBot', ctx: 'MessageContext', match: re.Match):
        bot.delete_room(ctx.room_id,ctx.person)
    
    @bot.hears(r"^\s*(usage|commands|\?).*",priority=90)
    def handle_usage(bot, ctx, match):
        supports_acknowledge = type(bot.alert_plugin).supports_acknowledge
        rendered = Template(USAGE_TEMPLATE).render(bot=bot, supports_acknowledge=supports_acknowledge)
        bot.say(ctx.room_id, rendered, markdown=True)
    
    @bot.hears(r"^(?P<cmd>\S+)\s+.*$",priority=99)
    def handle_unknown(bot: 'BaseChatBot', ctx: 'MessageContext', match: re.Match):
        bot.say(ctx.room_id,f"Unknown command {match.group('cmd')}. Please use @{bot.name} usage to see a list of commands")

    
    @bot.on_action
    def handle_actions(bot, action):
        """Processes Adaptive Card submissions (e.g. incident prompt from help/emergency)."""
        # 1. Input Validation — merged submit data uses string "action" (see _incident_prompt_card).
        action_type = action.inputs.get("action")
        if action_type != "submit_incident":
            return

        # 2. Extract inputs: summary from Input.Text; is_emergency from Toggle or submit data ("true"/"false").
        summary = action.inputs.get("summary", "No summary provided")
        is_emergency = action.inputs.get("is_emergency") == "true"
        priority = AlertPriority.HIGH if is_emergency else AlertPriority.NORMAL
        
        # 3. Resolve Identity via Driver-HAL
        # This keeps the Engine purely based on ThaumPerson objects
        speaker = bot.get_person(action.personId)
        
        # 4. Engine Call
        create_incident_room(bot, summary, speaker, priority)
    # -- End Function handle_actions
# -- End Function bind_thaum_handlers
