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


def _jira_user_search_fallback(
    email_key: str,
    site_api_prefix: str,
    auth: Any,
    lookup: Optional[Any],
) -> Optional[str]:
    """
    Jira ``GET /rest/api/3/user/search`` when lookup did not yield a jira platform id
    (e.g. ``lookup_plugin = null`` or LDAP-only cache).
    """
    url = f"{site_api_prefix}/rest/api/3/user/search"
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            params={"query": email_key, "maxResults": 50},
            auth=auth,
            timeout=timeout_pair(15.0),
        )
        response.raise_for_status()
    except Exception as e:
        logger.debug("Jira user/search fallback failed for %s: %s", email_key, e)
        return None

    users = response.json()
    if not isinstance(users, list):
        return None

    def _merge_from(u: dict) -> Optional[str]:
        account_id = str((u.get("accountId") or "")).strip()
        if not account_id:
            return None
        if lookup is not None:
            frag = ThaumPerson(
                email=email_key,
                platform_ids={"jira": account_id},
                source_plugin="jira",
            )
            display_name = str((u.get("displayName") or "")).strip()
            if display_name:
                frag.display_name = display_name
            try:
                lookup.merge_person(frag)
            except Exception as e:
                logger.warning(
                    "Jira merge_person cache update failed for %s (accountId=%s): %s",
                    email_key,
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
        if not isinstance(u, dict):
            continue
        email_addr = str((u.get("emailAddress") or "")).strip().lower()
        account_id = str((u.get("accountId") or "")).strip()
        if account_id and email_addr == email_key:
            return _merge_from(u)

    for u in users:
        if not isinstance(u, dict):
            continue
        account_id = str((u.get("accountId") or "")).strip()
        if account_id:
            return _merge_from(u)

    return None


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
            person = lookup.get_person_by_email(key)
        except Exception as e:
            logger.debug("Jira lookup get_person_by_email failed for %s: %s", key, e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(
                    logger,
                    "get_person_by_email traceback",
                    traceback.format_exc(),
                    LogLevel.SPAM,
                )
            person = None
        if person is not None:
            jid = person.platform_ids.get("jira")
            if jid:
                return jid

    return _jira_user_search_fallback(key, site_api_prefix, auth, lookup)
