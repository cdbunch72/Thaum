# thaum/engine.py
# Copyright 2026 <<Name>>. All rights reserved.

import logging
import datetime
from typing import Optional,List, TYPE_CHECKING
from thaum.types import ThaumPerson,AlertPriority
from jinja2 import Environment, StrictUndefined

if TYPE_CHECKING:
    from bots.base import BaseChatBot

logger = logging.getLogger("thaum.engine")

jinja_env = Environment(undefined=StrictUndefined)


def create_incident_room(bot: 'BaseChatBot', summary: str, speaker: ThaumPerson, priority=AlertPriority.NORMAL) -> Optional[str]:
    """Orchestrates room creation and plugin triggering."""
    try:
        template_str = getattr(bot, 'room_title_template', "Incident: {summary}")
        sender = speaker.for_display()
        template = jinja_env.from_string(template_str)
        context = {
            "summary": summary[:30],
            "requester_name": speaker.for_display(),
            "team_description": bot.config.team_description,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        room_title = template.render(**context)
        room_id = bot.create_room(room_title)
        
        # Add participants (bot.responders is a list of ThaumPerson)
        bot.add_members(room_id, [speaker] + bot.responders)
        bot.say(room_id, f"**Summary:** {summary}")
        # Trigger plugin
        (short_id,jira_id)=bot.alert_plugin.trigger_alert(summary, room_id, speaker, priority)
        
        bot.logger.verbose(f"Room {room_title} ({room_id}) initialized for alert {short_id}.")
        return room_id
    except Exception as e:
        bot.logger.error(f"Engine failure in create_incident_room: {e}")
        return None
# -- End Function create_incident_room

def acknowledge_incident(bot: 'BaseChatBot', alias: str, person: ThaumPerson) -> None:
    """Coordinates alert acknowledgment via the plugin."""
    try:
        person_name = person.for_display()
        bot.alert_plugin.acknowledge_alert(alias, person_name)
    except Exception as e:
        logger.error(f"Engine failure in acknowledge_incident: {e}")
# -- End Function acknowledge_incident
