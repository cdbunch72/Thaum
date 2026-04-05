# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/payload.py
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from thaum.types import AlertPriority, RespondersList, ThaumPerson


def responders_list_to_jira_payload(
    responders: RespondersList,
    resolve_email_to_account_id: Callable[[str], Optional[str]],
    logger: logging.Logger,
) -> list[dict[str, str]]:
    """
    Convert typed responders into Jira alert responder dicts.

    Team -> {"type": "team", "id": "<teamId>"}
    Person -> {"type": "user", "id": "<accountId>"}
    """
    payload: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for team in responders.teams:
        tid = (team.alert_id or "").strip()
        if not tid:
            continue
        key = ("team", tid)
        if key in seen:
            continue
        seen.add(key)
        payload.append({"type": "team", "id": tid})

    for person in responders.people:
        account_id = resolve_email_to_account_id(person.email)
        if not account_id:
            logger.warning("Jira responder email '%s' did not resolve to accountId", person.email)
            continue
        key = ("user", account_id)
        if key in seen:
            continue
        seen.add(key)
        payload.append({"type": "user", "id": account_id})

    return payload
# -- End Function responders_list_to_jira_payload


def post_alert(
    url: str,
    alert: dict[str, Any],
    headers: dict[str, str],
    auth: Any,
    timeout: float = 15,
) -> requests.Response:
    return requests.post(
        url,
        data=json.dumps(alert),
        headers=headers,
        auth=auth,
        timeout=timeout,
    )
# -- End Function post_alert


def parse_created_alert_id(response: requests.Response) -> str:
    jira_alert_id = ""
    try:
        resp_json = response.json()
        jira_alert_id = str(resp_json.get("alertId") or resp_json.get("id") or "")
    except Exception:
        jira_alert_id = ""
    return jira_alert_id
# -- End Function parse_created_alert_id


def build_sender_extra_properties(sender: ThaumPerson, plugin_name: str) -> dict[str, str]:
    """
    Sender object for Jira ``extraProperties`` (no email — privacy).

    ``name`` uses display name only; if absent, ``"Someone"`` (email is never sent).
    ``bot_person_id`` is the chat platform person id for ``plugin_name``, or empty string.
    """
    display = (sender.display_name or "").strip() or "Someone"
    pid = (sender.platform_ids or {}).get(plugin_name, "") or ""
    return {"name": display, "bot_person_id": pid}
# -- End Function build_sender_extra_properties


def build_trigger_alert_body(
    summary: str,
    bot_name: str,
    room_id: str,
    sender: ThaumPerson,
    priority: AlertPriority,
    priority_normal: str,
    priority_high: str,
    short_id: str,
    responders_payload: list[dict[str, str]],
    bot_key: str,
    plugin_name: str,
) -> dict[str, Any]:
    severity = priority_high if priority == AlertPriority.HIGH else priority_normal
    alert: dict[str, Any] = {
        "message": summary,
        "source": bot_name,
        "alias": f"THAUM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{short_id}",
        "priority": severity,
        "responders": responders_payload,
        "extraProperties": {
            "roomid": room_id,
            "sender": build_sender_extra_properties(sender, plugin_name),
            "short_id": short_id,
            "bot_key": bot_key,
        },
    }
    if priority == AlertPriority.HIGH:
        alert["tags"] = ["OverrideQuietHours"]
    return alert
# -- End Function build_trigger_alert_body
