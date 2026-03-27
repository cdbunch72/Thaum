# alerts/plugins/jira.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import requests
from pydantic import ConfigDict
from requests.auth import HTTPBasicAuth

from alerts.base import BaseAlertPlugin, BaseAlertPluginConfig
from thaum.types import AlertPriority, ResolvedSecret, RespondersList, ThaumPerson, ThaumTeam


class JiraAlertPluginConfig(BaseAlertPluginConfig):
    plugin: str = "jira"
    site_url: str
    cloud_id: str
    user: str
    api_token: ResolvedSecret
    responders: list[str]
    priority_normal: str = "P3"
    priority_high: str = "P2"
    status_webhook_bearer: str

    model_config = ConfigDict(extra="allow")
# -- End Class JiraAlertPluginConfig


class JiraPlugin(BaseAlertPlugin):
    supports_status_webhooks: bool = True

    def __init__(self, config: JiraAlertPluginConfig):
        super().__init__(config)
        self.cfg = config
        self.api_prefix = f"https://api.atlassian.com/jsm/ops/api/{self.cfg.cloud_id}"
        self.site_api_prefix = self.cfg.site_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.auth = HTTPBasicAuth(self.cfg.user, self.cfg.api_token.get_secret_value())

        # Caches
        self._team_name_by_folded: dict[str, str] = {}
    # -- End Method __init__

    def attach_bot(self, bot) -> None:
        super().attach_bot(bot)
        # Warm team cache once the bot reference exists (ThaumTeam requires bot).
        try:
            self._refresh_team_cache()
        except Exception as e:
            self.logger.warning("Could not prewarm Jira team cache: %s", e)
    # -- End Method attach_bot

    def validate_status_webhook_authorization(self, authorization_header_value: Optional[str]) -> bool:
        """Jira status webhooks: static Bearer using canonical JSON, or disabled when config is ''."""
        return self._validate_static_webhook_bearer(
            authorization_header_value,
            self.cfg.status_webhook_bearer,
        )
    # -- End Method validate_status_webhook_authorization

    def _canonical_team_ref(self, team_ref: str) -> str:
        """Normalize team refs like 'team:Name' or 'team:team - Name'."""
        name = team_ref.strip()
        if name.lower().startswith("team:"):
            name = name[5:].strip()
        canonical = self._team_name_by_folded.get(name.casefold())
        return canonical if canonical else name
    # -- End Method _canonical_team_ref

    def _refresh_team_cache(self) -> None:
        """Warm cache with all JSM Ops teams (including teams not referenced in config)."""
        if self._team_name_by_folded:
            return
        if not hasattr(self, "bot"):
            return

        url = f"{self.api_prefix}/v1/teams"
        response = requests.get(url, headers=self.headers, auth=self.auth, timeout=15)
        response.raise_for_status()
        payload = response.json()

        teams = payload.get("platformTeams", [])
        for item in teams:
            team_name = str(item.get("teamName", "")).strip()
            team_id = str(item.get("teamId", "")).strip()
            if not team_name or not team_id:
                continue
            t = ThaumTeam(bot=self.bot, team_name=team_name, alert_id=team_id, lookup_id=team_id)
            self._team_name_by_folded[team_name.casefold()] = team_name

            # Populate lookup cache so shared resolver logic can resolve team refs.
            lookup = getattr(self.bot, "lookup_plugin", None)
            if lookup is not None:
                try:
                    lookup.cache_team(t, bot_plugin_name="jira", team_id=team_id)
                except Exception as e:
                    self.logger.warning("Could not cache Jira team '%s' (%s): %s", team_name, team_id, e)
    # -- End Method _refresh_team_cache

    def _resolve_email_to_account_id(self, email: str) -> Optional[str]:
        key = email.strip().lower()
        if not key:
            return None

        # First try existing lookup cache mappings.
        lookup = getattr(self.bot, "lookup_plugin", None)
        if lookup is not None:
            try:
                cached = lookup.get_person_by_email(key)
            except Exception:
                cached = None
            if cached is not None:
                cached_id = (cached.platform_ids.get("jira"))
                if cached_id:
                    return cached_id

        # Jira Cloud user lookup via site URL (not api.atlassian.com).
        url = f"{self.site_api_prefix}/rest/api/3/user/search"
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            params={"query": key, "maxResults": 50},
            auth=self.auth,
            timeout=15,
        )
        response.raise_for_status()

        users = response.json()
        if not isinstance(users, list):
            return None

        # Prefer exact email matches when available.
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
                    except Exception:
                        pass
                return account_id

        # Fallback to first result with accountId.
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
                    except Exception:
                        pass
                return account_id

        return None
    # -- End Method _resolve_email_to_account_id

    def _resolve_config_responders(self) -> RespondersList:
        """Resolve plugin config responders into a typed RespondersList."""
        self._refresh_team_cache()
        lookup = getattr(self.bot, "lookup_plugin", None)
        if lookup is None:
            # Fallback keeps behavior if lookup plugin is unavailable for some reason.
            out = RespondersList()
            for raw in self.cfg.responders:
                ref = raw.strip()
                if not ref:
                    continue
                if ref.lower().startswith("person:"):
                    email = ref[7:].strip()
                    if email:
                        out += ThaumPerson(email=email)
                    continue
                if "@" in ref and not ref.lower().startswith("team:"):
                    out += ThaumPerson(email=ref)
            return out

        return lookup.resolve_responder_refs(
            self.bot,
            self.cfg.responders,
            source_plugin="jira_config",
            team_name_normalizer=self._canonical_team_ref,
        )
    # -- End Method _resolve_config_responders

    def _responders_list_to_jira_payload(self, responders: RespondersList) -> list[dict[str, str]]:
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
            account_id = self._resolve_email_to_account_id(person.email)
            if not account_id:
                self.logger.warning("Jira responder email '%s' did not resolve to accountId", person.email)
                continue
            key = ("user", account_id)
            if key in seen:
                continue
            seen.add(key)
            payload.append({"type": "user", "id": account_id})

        return payload
    # -- End Method _responders_list_to_jira_payload

    def validate_connection(self) -> bool:
        """Verify we can read team list and resolve responder references."""
        try:
            self._refresh_team_cache()
            _ = self._responders_list_to_jira_payload(self._resolve_config_responders())
            return True
        except Exception as e:
            self.logger.error("Jira connection/resolve validation failed: %s", e)
            return False
    # -- End Method validate_connection

    def trigger_alert(
        self,
        summary: str,
        room_id: str,
        sender: ThaumPerson,
        priority=AlertPriority.NORMAL,
    ) -> tuple[str, str]:
        short_id = self._generate_short_id(4)
        severity = self.cfg.priority_high if priority == AlertPriority.HIGH else self.cfg.priority_normal
        url = f"{self.api_prefix}/v1/alerts"

        responders_typed = self._resolve_config_responders()
        responders_payload = self._responders_list_to_jira_payload(responders_typed)

        alert = {
            "message": summary,
            "source": self.bot.name,
            "alias": f"THAUM-{datetime.now().strftime('%Y%m%d')}-{short_id}",
            "priority": severity,
            "responders": responders_payload,
            "extraProperties": {
                "roomid": room_id,
                "sender": sender.email,
                "short_id": short_id,
                "bot_key": self.bot.bot_key,
            },
        }
        if priority == AlertPriority.HIGH:
            alert["tags"] = ["OverrideQuietHours"]

        response = requests.post(
            url,
            data=json.dumps(alert),
            headers=self.headers,
            auth=self.auth,
            timeout=15,
        )
        response.raise_for_status()

        jira_alert_id = ""
        try:
            resp_json = response.json()
            jira_alert_id = str(resp_json.get("alertId") or resp_json.get("id") or "")
        except Exception:
            jira_alert_id = ""

        self.logger.info(
            "Jira alert created: severity=%s alias=%s responders=%d",
            severity,
            alert["alias"],
            len(responders_payload),
        )
        return short_id, jira_alert_id
    # -- End Method trigger_alert
# -- End Class JiraPlugin

def get_config_model():
    return JiraAlertPluginConfig
# -- End Function get_config_model


def create_instance_plugin(config: JiraAlertPluginConfig) -> JiraPlugin:
    return JiraPlugin(config)
# -- End Function create_instance_plugin

