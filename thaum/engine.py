# thaum/engine.py
# Copyright 2026 <<Name>>. All rights reserved.

import logging
from typing import Optional,List
from log_setup import SHOW_STACKTRACE
from thaum.identity import get_team,get_person_by_id,register_team,ThaumPerson,ThaumTeam

logger = logging.getLogger("thaum.engine")

def create_incident_room(bot, summary: str, is_emergency: bool, speaker_id: str) -> Optional[str]:
    """Orchestrates room creation and plugin triggering."""
    try:
        template = getattr(bot, 'room_title_template', "Incident: {summary}")
        sender = get_webex_name(bot, speaker_id)
        
        room_title = template.format(summary=summary[:30], sender=sender)
        room_id = bot.create_room(room_title)
        
        # Add participants (bot.responders is a list of emails/IDs)
        bot.add_members(room_id, [speaker_id] + bot.responders)
        bot.say(room_id, f"**Summary:** {summary}")
        
        # Trigger plugin
        bot.alert_plugin.trigger_alert(summary, is_emergency, room_id)
        
        logger.info(f"Room {room_id} initialized for alert.")
        return room_id
    except Exception as e:
        logger.error(f"Engine failure in create_incident_room: {e}", exc_info=SHOW_STACKTRACE)
        return None
# -- End Function create_incident_room

def acknowledge_incident(bot, alias: str, person_id: str) -> None:
    """Coordinates alert acknowledgment via the plugin."""
    try:
        person_name = get_webex_name(bot, person_id)
        bot.alert_plugin.acknowledge_alert(alias, person_name)
    except Exception as e:
        logger.error(f"Engine failure in acknowledge_incident: {e}", exc_info=SHOW_STACKTRACE)
# -- End Function acknowledge_incident

def get_team_members(bot, team_name: str) -> List[ThaumPerson]:
    """
    Orchestrator for roster resolution.
    1. Checks if local cache is fresh.
    2. If stale, tries to refresh from the Identity Plugin.
    3. If refresh fails, logs error and returns STALE cache (Fail-Safe).
    """
    # Get team from identity.py registry
    team = get_team(team_name)
    
    # Check if we need to refresh
    if team is None or not team.is_fresh():
        try:
            # 1. Attempt to fetch fresh data
            new_members = bot.identity_plugin.fetch_team(team_name)
            
            # 2. Update the cache
            team = register_team(team_name, new_members)
            bot.logger.info(f"Team '{team_name}' cache refreshed.")
            
        except Exception as e:
            # THE FAIL-SAFE:
            # If the API is down, we log the error but return the stale 'team' 
            # object if it existed. The system stays up!
            bot.logger.error(f"Identity refresh failed for '{team_name}': {e}. Using stale cache.")
            if not team:
                raise RuntimeError(f"Identity system for '{team_name}' is down and no cache exists.")

    return team.members