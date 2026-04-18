# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/users.py
from __future__ import annotations

import logging
import traceback
from typing import Any, Optional

import requests

from thaum.http_timeouts import timeout_pair
from log_setup import log_debug_blob
from thaum.types import LogLevel, ThaumPerson

logger = logging.getLogger("alerts.jira.users")


def resolve_email_to_account_id(
    email: str,
    bot: Any,
    site_api_prefix: str,
    auth: Any,
) -> Optional[str]:
    key = email.strip().lower()
    if not key:
        return None

    lookup = getattr(bot, "lookup_plugin", None)
    if lookup is not None:
        try:
            cached = lookup.get_person_by_email(key)
        except Exception as e:
            logger.debug("Jira lookup get_person_by_email failed for %s: %s", key, e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(
                    logger,
                    "get_person_by_email traceback",
                    traceback.format_exc(),
                    LogLevel.SPAM,
                )
            cached = None
        if cached is not None:
            cached_id = cached.platform_ids.get("jira")
            if cached_id:
                return cached_id

    url = f"{site_api_prefix}/rest/api/3/user/search"
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        params={"query": key, "maxResults": 50},
        auth=auth,
        timeout=timeout_pair(15.0),
    )
    response.raise_for_status()

    users = response.json()
    if not isinstance(users, list):
        return None

    for u in users:
        email_addr = str((u.get("emailAddress") or "")).strip().lower()
        account_id = str((u.get("accountId") or "")).strip()
        if account_id and email_addr == key:
            if lookup is not None:
                try:
                    display_name = str((u.get("displayName") or "")).strip()
                    fragment = ThaumPerson(
                        email=key,
                        platform_ids={"jira": account_id},
                    )
                    if display_name:
                        fragment.display_name = display_name
                        fragment.source_plugin = "jira"
                    lookup.merge_person(fragment)
                except Exception as e:
                    logger.warning(
                        "Jira merge_person cache update failed for %s (accountId=%s): %s",
                        key,
                        account_id,
                        e,
                    )
                    if logger.isEnabledFor(LogLevel.SPAM):
                        log_debug_blob(
                            logger,
                            "merge_person traceback",
                            traceback.format_exc(),
                            LogLevel.SPAM,
                        )
            return account_id

    for u in users:
        account_id = str((u.get("accountId") or "")).strip()
        if account_id:
            if lookup is not None:
                try:
                    display_name = str((u.get("displayName") or "")).strip()
                    fragment = ThaumPerson(
                        email=key,
                        platform_ids={"jira": account_id},
                    )
                    if display_name:
                        fragment.display_name = display_name
                        fragment.source_plugin = "jira"
                    lookup.merge_person(fragment)
                except Exception as e:
                    logger.warning(
                        "Jira merge_person cache update failed for %s (accountId=%s): %s",
                        key,
                        account_id,
                        e,
                    )
                    if logger.isEnabledFor(LogLevel.SPAM):
                        log_debug_blob(
                            logger,
                            "merge_person traceback",
                            traceback.format_exc(),
                            LogLevel.SPAM,
                        )
            return account_id

    return None
# -- End Function resolve_email_to_account_id
