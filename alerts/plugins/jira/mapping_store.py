# alerts/plugins/jira/mapping_store.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from gemstone_utils.db import get_session
from sqlalchemy import select

from alerts.plugins.jira.models import JiraAlertMap

# Matches ``build_trigger_alert_body`` alias suffix (same charset as BaseAlertPlugin._ALPHABET).
_SHORT_ID_TAIL_RE = re.compile(r"^THAUM-\d{8}-(?P<sid>[A-Z2-9]{4})$")


def parse_short_id_from_alias(alias: Optional[str]) -> str:
    if not alias or not isinstance(alias, str):
        return ""
    m = _SHORT_ID_TAIL_RE.match(alias.strip())
    if not m:
        return ""
    return m.group("sid")
# -- End Function parse_short_id_from_alias


def extra_properties_from_alert(alert: dict[str, Any]) -> dict[str, Any]:
    raw = alert.get("extraProperties")
    if isinstance(raw, dict):
        return raw
    details = alert.get("details")
    if isinstance(details, dict):
        ep = details.get("extraProperties")
        if isinstance(ep, dict):
            return ep
    return {}
# -- End Function extra_properties_from_alert


def upsert_pending_row(
    short_id: str,
    room_id: str,
    bot_key: str,
    alias: str,
    logger: logging.Logger,
) -> None:
    with get_session() as session:
        row = session.get(JiraAlertMap, short_id)
        if row is None:
            session.add(
                JiraAlertMap(
                    short_id=short_id,
                    room_id=room_id,
                    bot_key=bot_key,
                    alias=alias or None,
                    jira_alert_id=None,
                )
            )
        else:
            row.room_id = room_id
            row.bot_key = bot_key
            row.alias = alias or None
    logger.verbose("Jira alert map pending short_id=%s bot_key=%s", short_id, bot_key)
# -- End Function upsert_pending_row


def room_id_for_jira_alert(jira_alert_id: str, bot_key: str) -> Optional[str]:
    jid = (jira_alert_id or "").strip()
    if not jid:
        return None
    with get_session() as session:
        q = select(JiraAlertMap).where(
            JiraAlertMap.jira_alert_id == jid,
            JiraAlertMap.bot_key == bot_key,
        )
        row = session.scalars(q).first()
        if row is None:
            return None
        return row.room_id
# -- End Function room_id_for_jira_alert


def apply_create_webhook(
    *,
    jira_alert_id: str,
    short_id: str,
    bot_key: str,
    room_id_fallback: str,
    alias_fallback: Optional[str],
    logger: logging.Logger,
) -> None:
    jid = jira_alert_id.strip()
    sid = short_id.strip()
    if not jid or not sid:
        logger.warning("Jira Create webhook: missing alertId or short_id")
        return
    with get_session() as session:
        row = session.get(JiraAlertMap, sid)
        if row is None:
            rf = (room_id_fallback or "").strip()
            if not rf:
                logger.warning("Jira Create webhook: no existing row and no room_id for short_id=%s", sid)
                return
            session.add(
                JiraAlertMap(
                    short_id=sid,
                    room_id=rf,
                    bot_key=bot_key,
                    alias=alias_fallback,
                    jira_alert_id=jid,
                )
            )
        else:
            if row.bot_key != bot_key:
                logger.warning("Jira Create webhook: short_id %s belongs to another bot_key", sid)
                return
            row.jira_alert_id = jid
            if alias_fallback and not row.alias:
                row.alias = alias_fallback
    logger.verbose("Jira alert map linked short_id=%s jira_alert_id=%s", sid, jid)
# -- End Function apply_create_webhook
