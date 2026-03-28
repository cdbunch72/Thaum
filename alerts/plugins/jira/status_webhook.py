# alerts/plugins/jira/status_webhook.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from typing import Any, Optional

from alerts.plugins.jira.config import JiraAlertPluginConfig
from alerts.plugins.jira.mapping_store import (
    apply_create_webhook,
    extra_properties_from_alert,
    parse_short_id_from_alias,
    room_id_for_jira_alert,
)
from bots.base import BaseChatBot


def _bot_key_str(bot: BaseChatBot) -> str:
    return str(getattr(bot, "bot_key", None) or "")
# -- End Function _bot_key_str


def _display_name_for_username(bot: BaseChatBot, logger: logging.Logger, username: Optional[str]) -> str:
    u = (username or "").strip()
    if not u:
        return "Someone"
    if "@" in u:
        lookup = getattr(bot, "lookup_plugin", None)
        if lookup is not None:
            try:
                person = lookup.get_person_by_email(u)
                if person is not None:
                    return person.for_display()
            except Exception as e:
                logger.debug("lookup display name for %s failed: %s", u, e)
    return u
# -- End Function _display_name_for_username


def _resolve_room_id(*, bot_key: str, jira_alert_id: str, extras: dict[str, Any]) -> str:
    rid = room_id_for_jira_alert(jira_alert_id, bot_key)
    if rid:
        return rid
    for k in ("roomid", "room_id"):
        v = extras.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
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
    props_bk = str(extras.get("bot_key") or "").strip()
    if props_bk and bot_key and props_bk != bot_key:
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

    room_id = _resolve_room_id(bot_key=bot_key, jira_alert_id=jid, extras=extras)
    if not room_id:
        logger.warning("Jira status webhook action=%s could not resolve room for alertId=%s", action, jid)
        return

    if action == "Acknowledge":
        name = _display_name_for_username(bot, logger, alert.get("username"))
        bot.say(
            room_id,
            f"{name} has acknowledged the alert and should be joining you shortly. Allow time to login.",
        )
        return

    if action == "UnAcknowledge":
        name = _display_name_for_username(bot, logger, alert.get("username"))
        bot.say(
            room_id,
            f"{name} is not able to help you after all, escalating to next level. Thank you for your patience.",
        )
        return

    if action == "Escalate":
        if cfg.send_escalate_msg:
            bot.say(room_id, "The alert has been escalated, thank you for your patience.")
        return

    logger.debug("Jira status webhook unhandled action=%s", action)
# -- End Function handle_jira_status_webhook
