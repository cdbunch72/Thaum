# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/status_webhook.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jinja2 import Environment, StrictUndefined

from alerts.plugins.jira.config import JiraAlertPluginConfig
from alerts.plugins.jira.mapping_store import (
    apply_create_webhook,
    mapping_for_alias,
    mapping_for_jira_alert_id,
    parse_short_id_from_alias,
)
from bots.base import BaseChatBot
from thaum.types import ThaumPerson

_jinja_env = Environment(undefined=StrictUndefined)


def _bot_key_str(bot: BaseChatBot) -> str:
    return str(getattr(bot, "bot_key", None) or "")
# -- End Function _bot_key_str


def _sender_name_or_default(
    sender_name: Optional[str],
) -> str:
    return (sender_name or "").strip() or "Someone"
# -- End Function _sender_name_or_default


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
    sender_name: Optional[str],
    alert: dict[str, Any],
) -> dict[str, Any]:
    sender_name = _sender_name_or_default(sender_name)
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


def _alert_created_at_utc(alert: dict[str, Any]) -> Optional[datetime]:
    raw = alert.get("createdAt")
    if raw is None:
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
# -- End Function _alert_created_at_utc


def _is_recent_alert(alert: dict[str, Any], window: timedelta) -> bool:
    created = _alert_created_at_utc(alert)
    if created is None:
        return False
    return datetime.now(timezone.utc) - created < window
# -- End Function _is_recent_alert


def _say_status_message(
    bot: BaseChatBot,
    room_id: str,
    cfg: JiraAlertPluginConfig,
    template_str: str,
    ctx: dict[str, Any],
) -> None:
    markdown = _render_status_template(template_str, ctx)
    mention_differs = ctx.get("responder_mention") != ctx.get("responder_name")
    if cfg.status_mentions and mention_differs:
        plain_ctx = {**ctx, "responder_mention": ctx["responder_name"]}
        text = _render_status_template(template_str, plain_ctx)
        bot.say(room_id, text, markdown=markdown)
    else:
        bot.say(room_id, markdown)
# -- End Function _say_status_message


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

    if action == "Create":
        jid = str(alert.get("alertId") or "").strip()
        alias = str(alert.get("alias") or "").strip()
        short_id = parse_short_id_from_alias(alias)
        existing = mapping_for_alias(alias, bot_key) if alias and bot_key else None
        room_fb = (existing[1] if existing else "").strip()
        sender_fb = (existing[2] if existing else "").strip()
        if not bot_key:
            logger.warning("Jira Create webhook: bot has no bot_key")
            return
        apply_create_webhook(
            jira_alert_id=jid,
            bot_key=bot_key,
            alias=alias,
            short_id_fallback=short_id,
            room_id_fallback=room_fb,
            sender_name_fallback=sender_fb,
            logger=logger,
        )
        return

    jid = str(alert.get("alertId") or "").strip()
    if not jid:
        logger.debug("Jira status webhook action=%s missing alertId", action)
        return

    alias = str(alert.get("alias") or "").strip()
    room_id = ""
    sender_name = "Someone"

    mapping_by_alert = mapping_for_jira_alert_id(jid, bot_key)
    if mapping_by_alert is not None:
        room_id = (mapping_by_alert[1] or "").strip()
        sender_name = (mapping_by_alert[3] or "").strip() or "Someone"

    if not room_id and alias and bot_key:
        mapping_by_alias = mapping_for_alias(alias, bot_key)
        if mapping_by_alias is not None:
            room_id = (mapping_by_alias[1] or "").strip()
            sender_name = (mapping_by_alias[2] or "").strip() or "Someone"
    if not room_id:
        logger.warning("Jira status webhook action=%s could not resolve room for alertId=%s", action, jid)
        return

    ctx = _status_message_context(bot, cfg, logger, sender_name, alert)

    if action == "Acknowledge":
        _say_status_message(bot, room_id, cfg, cfg.status_ack_template, ctx)
        return

    if action == "UnAcknowledge":
        _say_status_message(bot, room_id, cfg, cfg.status_unack_template, ctx)
        return

    if action == "Escalate":
        if cfg.send_escalate_msg:
            _say_status_message(bot, room_id, cfg, cfg.status_escalate_template, ctx)
        return

    if action == "Close":
        window = timedelta(minutes=cfg.status_accidental_close_minutes)
        if _is_recent_alert(alert, window):
            _say_status_message(bot, room_id, cfg, cfg.status_accidental_close_template, ctx)
        return

    logger.debug("Jira status webhook unhandled action=%s", action)
# -- End Function handle_jira_status_webhook
