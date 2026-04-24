# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/engine.py
import logging
import json
from datetime import datetime, timezone
from typing import Optional,List, TYPE_CHECKING
from pathlib import Path
from thaum.types import AlertPriority, LogLevel, ThaumPerson
from jinja2 import Environment, StrictUndefined

if TYPE_CHECKING:
    from bots.base import BaseChatBot

logger = logging.getLogger("thaum.engine")

jinja_env = Environment(undefined=StrictUndefined)


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
        # #region agent log
        try:
            _typed = getattr(bot, "responders", None)
            _log = {
                "sessionId": "d2aafe",
                "runId": "pre-fix",
                "hypothesisId": "W1-W4",
                "location": "thaum/engine.py:create_incident_room:before_expand",
                "message": "Room responder expansion input",
                "data": {
                    "typed_people_count": len(getattr(_typed, "people", [])) if _typed is not None else 0,
                    "typed_teams_count": len(getattr(_typed, "teams", [])) if _typed is not None else 0,
                },
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            }
            _log_paths = [
                Path(__file__).resolve().parents[1] / "debug-d2aafe.log",
                Path("/var/log/thaum") / "debug-d2aafe.log",
            ]
            for _log_path in _log_paths:
                try:
                    _log_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                try:
                    with open(_log_path, "a", encoding="utf-8") as _dbg:
                        _dbg.write(json.dumps(_log, default=str) + "\n")
                except Exception:
                    pass
        except Exception:
            pass
        # #endregion
        responders = bot.responders.get_responders()
        # #region agent log
        try:
            _log = {
                "sessionId": "d2aafe",
                "runId": "pre-fix",
                "hypothesisId": "W1-W4",
                "location": "thaum/engine.py:create_incident_room:after_expand",
                "message": "Room responder expansion output",
                "data": {
                    "expanded_responder_count": len(responders),
                },
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            }
            _log_paths = [
                Path(__file__).resolve().parents[1] / "debug-d2aafe.log",
                Path("/var/log/thaum") / "debug-d2aafe.log",
            ]
            for _log_path in _log_paths:
                try:
                    _log_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                try:
                    with open(_log_path, "a", encoding="utf-8") as _dbg:
                        _dbg.write(json.dumps(_log, default=str) + "\n")
                except Exception:
                    pass
        except Exception:
            pass
        # #endregion
        bot.add_members(room_id, [speaker, *responders])
        bot.say(room_id, f"**Summary:** {summary}")
        short_id, alert_id = bot.alert_plugin.trigger_alert(summary, room_id, speaker, priority)
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
