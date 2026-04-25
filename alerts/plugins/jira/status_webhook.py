# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/status_webhook.py
from __future__ import annotations

import logging
import json
import time
from typing import Any, Optional

from jinja2 import Environment, StrictUndefined

from alerts.plugins.jira.config import JiraAlertPluginConfig
from alerts.plugins.jira.mapping_store import (
    apply_create_webhook,
    extra_properties_from_alert,
    mapping_for_short_id,
    parse_short_id_from_alias,
    room_id_for_jira_alert,
)
from bots.base import BaseChatBot
from thaum.types import ThaumPerson

_jinja_env = Environment(undefined=StrictUndefined)
_DEBUG_LOG_PATH = "/var/log/thaum/debug-d09bdd.log"


def _debug_log(
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
) -> None:
    # region agent log
    payload = {
        "sessionId": "d09bdd",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass
    # endregion agent log
# -- End Function _debug_log


def _bot_key_str(bot: BaseChatBot) -> str:
    return str(getattr(bot, "bot_key", None) or "")
# -- End Function _bot_key_str


def _sender_name_and_bot_person_id(
    bot: BaseChatBot,
    logger: logging.Logger,
    extras: dict[str, Any],
) -> tuple[str, str]:
    pid_fallback = str(extras.get("sender_bot_person_id") or "").strip()
    raw = extras.get("sender")
    if isinstance(raw, dict):
        name = str(raw.get("name") or "").strip() or "Someone"
        pid = str(raw.get("bot_person_id") or "").strip() or pid_fallback
        return name, pid
    if isinstance(raw, str) and raw.strip():
        u = raw.strip()
        if "@" in u:
            lookup = getattr(bot, "lookup_plugin", None)
            if lookup is not None:
                try:
                    person = lookup.get_person_by_email(u)
                    if person is not None:
                        return person.for_display, ""
                except Exception as e:
                    logger.debug("legacy sender email lookup failed: %s", e)
            return "Someone", ""
        return u, pid_fallback
    return "Someone", pid_fallback
# -- End Function _sender_name_and_bot_person_id


def _responder_name_and_person(
    bot: BaseChatBot,
    logger: logging.Logger,
    username: Optional[str],
) -> tuple[str, Optional[ThaumPerson]]:
    u = (username or "").strip()
    if not u:
        return "Someone", None
    if "@" in u:
        lookup = getattr(bot, "lookup_plugin", None)
        if lookup is not None:
            try:
                person = lookup.get_person_by_email(u)
                if person is not None:
                    return person.for_display, person
            except Exception as e:
                logger.debug("responder lookup for %s failed: %s", u, e)
        return "Someone", None
    return u, None
# -- End Function _responder_name_and_person


def _status_message_context(
    bot: BaseChatBot,
    cfg: JiraAlertPluginConfig,
    logger: logging.Logger,
    extras: dict[str, Any],
    alert: dict[str, Any],
) -> dict[str, Any]:
    sender_name, sender_pid = _sender_name_and_bot_person_id(bot, logger, extras)
    if cfg.status_mentions and sender_pid:
        sender_mention = bot.format_mention(sender_pid)
    else:
        sender_mention = sender_name

    responder_name, responder_person = _responder_name_and_person(
        bot, logger, alert.get("username")
    )
    if cfg.status_mentions and responder_person is not None:
        responder_mention = bot.format_mention(responder_person)
    else:
        responder_mention = responder_name

    return {
        "team_description": bot.team_description,
        "sender_name": sender_name,
        "sender_mention": sender_mention,
        "responder_name": responder_name,
        "responder_mention": responder_mention,
    }
# -- End Function _status_message_context


def _render_status_template(template_str: str, context: dict[str, Any]) -> str:
    return _jinja_env.from_string(template_str).render(**context)
# -- End Function _render_status_template


def _resolve_room_id(*, bot_key: str, jira_alert_id: str, extras: dict[str, Any]) -> str:
    rid = room_id_for_jira_alert(jira_alert_id, bot_key)
    _debug_log(
        run_id="initial",
        hypothesis_id="H2",
        location="alerts/plugins/jira/status_webhook.py:_resolve_room_id",
        message="room lookup primary result",
        data={
            "jira_alert_id": jira_alert_id,
            "bot_key": bot_key,
            "resolved_from_mapping": bool(rid),
            "extras_keys": sorted([str(k) for k in extras.keys()]),
        },
    )
    if rid:
        return rid
    for k in ("roomid", "room_id", "roomId"):
        v = extras.get(k)
        if isinstance(v, str) and v.strip():
            _debug_log(
                run_id="initial",
                hypothesis_id="H3",
                location="alerts/plugins/jira/status_webhook.py:_resolve_room_id",
                message="room fallback from extras",
                data={"fallback_key": k, "room_present": True},
            )
            return v.strip()
    alias = str(extras.get("alias") or "").strip()
    sid = parse_short_id_from_alias(alias)
    if sid and bot_key:
        short_map = mapping_for_short_id(sid, bot_key)
        short_room = (short_map[1] or "").strip() if short_map else ""
        if short_room:
            _debug_log(
                run_id="initial",
                hypothesis_id="H7",
                location="alerts/plugins/jira/status_webhook.py:_resolve_room_id",
                message="room resolved from alias->short mapping",
                data={"short_id": sid, "has_short_mapping": True},
            )
            return short_room
    _debug_log(
        run_id="initial",
        hypothesis_id="H1",
        location="alerts/plugins/jira/status_webhook.py:_resolve_room_id",
        message="room unresolved after all fallbacks",
        data={"jira_alert_id": jira_alert_id, "bot_key": bot_key},
    )
    return ""
# -- End Function _resolve_room_id


def handle_jira_status_webhook(
    *,
    bot: BaseChatBot,
    cfg: JiraAlertPluginConfig,
    logger: logging.Logger,
    payload: dict[str, Any],
) -> None:
    action = str(payload.get("action") or "")
    alert = payload.get("alert")
    if not isinstance(alert, dict):
        alert = {}
    bot_key = _bot_key_str(bot)
    extras = extra_properties_from_alert(alert)
    _debug_log(
        run_id="initial",
        hypothesis_id="H4",
        location="alerts/plugins/jira/status_webhook.py:handle_jira_status_webhook",
        message="webhook entry",
        data={
            "action": action,
            "alert_id": str(alert.get("alertId") or ""),
            "has_alias": bool(str(alert.get("alias") or "").strip()),
            "has_extras": bool(extras),
            "bot_key": bot_key,
        },
    )
    props_bk = str(extras.get("bot_key") or "").strip()
    if props_bk and bot_key and props_bk != bot_key:
        _debug_log(
            run_id="initial",
            hypothesis_id="H4",
            location="alerts/plugins/jira/status_webhook.py:handle_jira_status_webhook",
            message="bot_key mismatch prevents processing",
            data={"props_bot_key": props_bk, "bot_key": bot_key, "action": action},
        )
        logger.warning("Jira status webhook bot_key mismatch (url vs extraProperties)")
        return

    if action == "Create":
        jid = str(alert.get("alertId") or "").strip()
        short_id = str(extras.get("short_id") or "").strip()
        if not short_id:
            short_id = parse_short_id_from_alias(str(alert.get("alias") or ""))
        alias_fb = str(alert.get("alias") or "").strip() or None
        room_fb = str(extras.get("roomid") or extras.get("room_id") or "").strip()
        if not bot_key:
            logger.warning("Jira Create webhook: bot has no bot_key")
            return
        _debug_log(
            run_id="initial",
            hypothesis_id="H6",
            location="alerts/plugins/jira/status_webhook.py:handle_jira_status_webhook",
            message="processing create webhook",
            data={
                "alert_id": jid,
                "short_id": short_id,
                "has_room_fallback": bool(room_fb),
                "has_alias_fallback": bool(alias_fb),
            },
        )
        apply_create_webhook(
            jira_alert_id=jid,
            short_id=short_id,
            bot_key=bot_key,
            room_id_fallback=room_fb,
            alias_fallback=alias_fb,
            logger=logger,
        )
        return

    jid = str(alert.get("alertId") or "").strip()
    if not jid:
        logger.debug("Jira status webhook action=%s missing alertId", action)
        return

    alias = str(alert.get("alias") or "").strip()
    short_from_alias = parse_short_id_from_alias(alias)
    short_map = mapping_for_short_id(short_from_alias, bot_key) if short_from_alias and bot_key else None
    _debug_log(
        run_id="initial",
        hypothesis_id="H7",
        location="alerts/plugins/jira/status_webhook.py:handle_jira_status_webhook",
        message="non-create webhook alias mapping context",
        data={
            "action": action,
            "has_alias": bool(alias),
            "short_from_alias": short_from_alias,
            "has_short_mapping": bool(short_map),
            "short_mapping_has_room": bool(short_map and (short_map[1] or "").strip()),
            "short_mapping_has_alert_id": bool(short_map and (short_map[0] or "").strip()),
        },
    )

    room_id = _resolve_room_id(bot_key=bot_key, jira_alert_id=jid, extras=extras)
    if not room_id and short_map:
        room_id = (short_map[1] or "").strip()
        if room_id:
            _debug_log(
                run_id="initial",
                hypothesis_id="H7",
                location="alerts/plugins/jira/status_webhook.py:handle_jira_status_webhook",
                message="room fallback from short mapping context",
                data={"action": action, "short_from_alias": short_from_alias},
            )
    if not room_id:
        logger.warning("Jira status webhook action=%s could not resolve room for alertId=%s", action, jid)
        return

    ctx = _status_message_context(bot, cfg, logger, extras, alert)

    if action == "Acknowledge":
        text = _render_status_template(cfg.status_ack_template, ctx)
        _debug_log(
            run_id="initial",
            hypothesis_id="H5",
            location="alerts/plugins/jira/status_webhook.py:handle_jira_status_webhook",
            message="sending acknowledge status message",
            data={
                "room_id_present": bool(room_id),
                "text_len": len(text),
                "status_mentions": bool(cfg.status_mentions),
                "markdown_value_type": "none",
            },
        )
        bot.say(room_id, text)
        return

    if action == "UnAcknowledge":
        text = _render_status_template(cfg.status_unack_template, ctx)
        bot.say(room_id, text)
        return

    if action == "Escalate":
        if cfg.send_escalate_msg:
            text = _render_status_template(cfg.status_escalate_template, ctx)
            bot.say(room_id, text)
        return

    logger.debug("Jira status webhook unhandled action=%s", action)
# -- End Function handle_jira_status_webhook
