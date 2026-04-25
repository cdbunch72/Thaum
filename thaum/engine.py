# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/engine.py
import logging
from datetime import datetime, timezone
from typing import Optional,List, TYPE_CHECKING
from thaum.types import AlertPriority, LogLevel, ThaumPerson
from jinja2 import Environment, StrictUndefined

if TYPE_CHECKING:
    from bots.base import BaseChatBot

logger = logging.getLogger("thaum.engine")

jinja_env = Environment(undefined=StrictUndefined)


def _render_customer_service_message(bot: "BaseChatBot", context: dict) -> str:
    template_raw = getattr(bot, "customer_service_message_template", None)
    if template_raw is None:
        template_raw = (
            "Thank you for your patience.  The next available person from "
            "{{ team_description }} will be with you shortlly."
        )
    template_text = str(template_raw)
    if not template_text.strip():
        return ""
    try:
        return jinja_env.from_string(template_text).render(**context).strip()
    except Exception as e:
        bot.logger.warning("Could not render customer service message template: %s", e)
        return ""


def create_incident_room(bot: 'BaseChatBot', summary: str, speaker: ThaumPerson, priority=AlertPriority.NORMAL) -> Optional[str]:
    """Orchestrates room creation and plugin triggering."""
    try:
        template_str = getattr(bot, 'room_title_template', "Incident: {summary}")
        sender = speaker.for_display
        template = jinja_env.from_string(template_str)
        context = {
            "summary": summary[:30],
            "requester_name": speaker.for_display,
            "team_description": bot.team_description,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
        room_title = template.render(**context)
        room_id = bot.create_room(room_title)
        responders = bot.responders.get_responders()
        bot.add_members(room_id, [speaker, *responders])
        customer_service_message = _render_customer_service_message(bot, context)
        if customer_service_message:
            bot.say(room_id, customer_service_message)
        bot.say(room_id, f"**Summary:** {summary}")
        short_id, alert_id = bot.alert_plugin.trigger_alert(summary, room_id, speaker, priority)
        if short_id:
            bot.say(room_id, f"Alert sent: {short_id}")
        
        if alert_id:
            bot.logger.log(
                LogLevel.VERBOSE,
                "Room %s (%s) initialized for alert %s (%s).",
                room_title,
                room_id,
                short_id,
                alert_id,
            )
        else:
            bot.logger.log(
                LogLevel.VERBOSE,
                "Room %s (%s) initialized for alert %s.",
                room_title,
                room_id,
                short_id,
            )
        return room_id
    except Exception as e:
        bot.logger.error(f"Engine failure in create_incident_room: {e}")
        return None
# -- End Function create_incident_room

def acknowledge_incident(bot: 'BaseChatBot', alias: str, person: ThaumPerson) -> None:
    """Coordinates alert acknowledgment via the plugin."""
    try:
        person_name = person.for_display
        bot.alert_plugin.acknowledge_alert(alias, person_name)
    except Exception as e:
        logger.error(f"Engine failure in acknowledge_incident: {e}")
# -- End Function acknowledge_incident
