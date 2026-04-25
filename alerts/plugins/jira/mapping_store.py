# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/mapping_store.py
from __future__ import annotations

import logging
import re
from typing import Optional

from gemstone_utils.db import get_session
from sqlalchemy import select

from alerts.plugins.jira.models import JiraAlertMap


def _verbose(logger: logging.Logger, msg: str, *args: object) -> None:
    fn = getattr(logger, "verbose", None)
    if callable(fn):
        fn(msg, *args)
    else:
        logger.debug(msg, *args)


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


def upsert_pending_row(
    bot_key: str,
    alias: str,
    short_id: str,
    room_id: str,
    sender_name: str,
    logger: logging.Logger,
) -> None:
    bk = (bot_key or "").strip()
    al = (alias or "").strip()
    sid = (short_id or "").strip()
    rid = (room_id or "").strip()
    snd = (sender_name or "").strip() or "Someone"
    if not bk or not al or not sid or not rid:
        logger.warning("Jira alert map pending skipped: missing bot_key/alias/short_id/room_id")
        return
    with get_session() as session:
        with session.begin():
            row = session.get(JiraAlertMap, {"bot_key": bk, "alias": al})
            if row is None:
                session.add(
                    JiraAlertMap(
                        bot_key=bk,
                        alias=al,
                        short_id=sid,
                        room_id=rid,
                        sender_name=snd,
                        jira_alert_id=None,
                    )
                )
            else:
                row.short_id = sid
                row.room_id = rid
                row.sender_name = snd
    _verbose(logger, "Jira alert map pending alias=%s short_id=%s bot_key=%s", al, sid, bk)
# -- End Function upsert_pending_row


def mapping_for_jira_alert_id(
    jira_alert_id: str, bot_key: str
) -> Optional[tuple[str, str, Optional[str], str]]:
    jid = (jira_alert_id or "").strip()
    bk = (bot_key or "").strip()
    if not jid or not bk:
        return None
    with get_session() as session:
        q = select(JiraAlertMap).where(
            JiraAlertMap.jira_alert_id == jid,
            JiraAlertMap.bot_key == bk,
        )
        row = session.scalars(q).first()
        if row is None:
            return None
        return row.alias, row.room_id, row.jira_alert_id, row.sender_name
# -- End Function mapping_for_jira_alert_id


def room_id_for_jira_alert(jira_alert_id: str, bot_key: str) -> Optional[str]:
    m = mapping_for_jira_alert_id(jira_alert_id, bot_key)
    if m is None:
        return None
    return m[1]
# -- End Function room_id_for_jira_alert


def mapping_for_alias(alias: str, bot_key: str) -> Optional[tuple[Optional[str], str, str]]:
    al = (alias or "").strip()
    bk = (bot_key or "").strip()
    if not al or not bk:
        return None
    with get_session() as session:
        row = session.get(JiraAlertMap, {"bot_key": bk, "alias": al})
        if row is None:
            return None
        return row.jira_alert_id, row.room_id, row.sender_name
# -- End Function mapping_for_alias


def mapping_for_short_id(short_id: str, bot_key: str) -> Optional[tuple[Optional[str], str, str]]:
    sid = (short_id or "").strip()
    bk = (bot_key or "").strip()
    if not sid or not bk:
        return None
    with get_session() as session:
        q = select(JiraAlertMap).where(
            JiraAlertMap.short_id == sid,
            JiraAlertMap.bot_key == bk,
        )
        row = session.scalars(q).first()
        if row is None:
            return None
        return row.jira_alert_id, row.room_id, row.alias
# -- End Function mapping_for_short_id


def apply_create_webhook(
    *,
    jira_alert_id: str,
    bot_key: str,
    alias: str,
    short_id_fallback: str,
    room_id_fallback: str,
    sender_name_fallback: str,
    logger: logging.Logger,
) -> None:
    jid = jira_alert_id.strip()
    bk = (bot_key or "").strip()
    al = (alias or "").strip()
    sid_fb = (short_id_fallback or "").strip()
    if not jid or not bk or not al:
        logger.warning("Jira Create webhook: missing alertId, bot_key, or alias")
        return
    with get_session() as session:
        with session.begin():
            row = session.get(JiraAlertMap, {"bot_key": bk, "alias": al})
            if row is None:
                rf = (room_id_fallback or "").strip()
                if not rf:
                    logger.warning(
                        "Jira Create webhook: no existing row and no room_id for alias=%s", al
                    )
                    return
                sid = sid_fb or parse_short_id_from_alias(al)
                if not sid:
                    logger.warning(
                        "Jira Create webhook: no existing row and no short_id for alias=%s", al
                    )
                    return
                session.add(
                    JiraAlertMap(
                        bot_key=bk,
                        alias=al,
                        short_id=sid,
                        room_id=rf,
                        sender_name=(sender_name_fallback or "").strip() or "Someone",
                        jira_alert_id=jid,
                    )
                )
            else:
                row.jira_alert_id = jid
    _verbose(logger, "Jira alert map linked alias=%s jira_alert_id=%s", al, jid)
# -- End Function apply_create_webhook
