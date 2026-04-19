# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/teams.py
from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from thaum.http_timeouts import timeout_pair
from thaum.types import ThaumTeam


def canonical_team_ref(team_ref: str, team_name_by_folded: dict[str, str]) -> str:
    """Normalize team refs like 'team:Name' or 'team:team - Name'."""
    name = team_ref.strip()
    if name.lower().startswith("team:"):
        name = name[5:].strip()
    canonical = team_name_by_folded.get(name.casefold())
    return canonical if canonical else name
# -- End Function canonical_team_ref


def refresh_team_cache(
    bot: Any,
    api_prefix: str,
    headers: dict[str, str],
    auth: Any,
    team_name_by_folded: dict[str, str],
    team_id_by_folded: dict[str, str],
    logger: logging.Logger,
) -> None:
    """Warm cache with all JSM Ops teams (including teams not referenced in config)."""
    if team_name_by_folded:
        return

    url = f"{api_prefix}/v1/teams"
    response = requests.get(url, headers=headers, auth=auth, timeout=timeout_pair(15.0))
    response.raise_for_status()
    payload = response.json()

    # #region agent log
    try:
        with open(
            "/var/log/thaum/debug-ce1c69.log",
            "a",
            encoding="utf-8",
        ) as _f:
            _ptype = type(payload).__name__
            _keys = list(payload.keys())[:12] if isinstance(payload, dict) else None
            _alen = len(payload) if isinstance(payload, list) else None
            _f.write(
                json.dumps(
                    {
                        "sessionId": "ce1c69",
                        "hypothesisId": "H4",
                        "location": "jira/teams.py:refresh_team_cache",
                        "message": "JSM teams API payload shape",
                        "data": {
                            "payload_type": _ptype,
                            "dict_keys_sample": _keys,
                            "list_len": _alen,
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion

    teams = payload.get("platformTeams", [])
    for item in teams:
        team_name = str(item.get("teamName", "")).strip()
        team_id = str(item.get("teamId", "")).strip()
        if not team_name or not team_id:
            continue
        t = ThaumTeam(bot=bot, team_name=team_name, alert_id=team_id, lookup_id=team_id)
        team_name_by_folded[team_name.casefold()] = team_name
        team_id_by_folded[team_name.casefold()] = team_id

        lookup = getattr(bot, "lookup_plugin", None)
        if lookup is not None:
            try:
                lookup.cache_team(t, bot_plugin_name="jira", team_id=team_id)
            except Exception as e:
                logger.warning("Could not cache Jira team '%s' (%s): %s", team_name, team_id, e)
# -- End Function refresh_team_cache
