# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/plugins/jira/plugin.py
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from requests.auth import HTTPBasicAuth

from log_setup import log_debug_blob
from alerts.base import BaseAlertPlugin
from alerts.plugins.jira.config import JiraAlertPluginConfig
from alerts.plugins.jira.mapping_store import upsert_pending_row
from alerts.plugins.jira.payload import (
    build_trigger_alert_body,
    post_alert,
    responders_list_to_jira_payload,
)
from alerts.plugins.jira.status_webhook import handle_jira_status_webhook
from alerts.plugins.jira.teams import canonical_team_ref, refresh_team_cache
from alerts.plugins.jira.users import resolve_email_to_account_id as resolve_email_to_account_id_impl
from thaum.types import AlertPriority, LogLevel, RespondersList, ThaumPerson


class JiraPlugin(BaseAlertPlugin):
    supports_status_webhooks: bool = True
    supports_acknowledge: bool = False

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

        self._team_name_by_folded: dict[str, str] = {}
        self._team_id_by_folded: dict[str, str] = {}
    # -- End Method __init__

    def attach_bot(self, bot) -> None:
        super().attach_bot(bot)
        try:
            self._refresh_team_cache()
        except Exception as e:
            self.logger.warning("Could not prewarm Jira team cache: %s", e)
            if self.logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(
                    self.logger,
                    "attach_bot prewarm traceback",
                    traceback.format_exc(),
                    LogLevel.SPAM,
                )
    # -- End Method attach_bot

    def validate_status_webhook_authorization(self, authorization_header_value: Optional[str]) -> bool:
        """Jira status webhooks: static Bearer using canonical JSON, or disabled when config is ''."""
        return self._validate_static_webhook_bearer(
            authorization_header_value,
            self.cfg.status_webhook_bearer,
        )
    # -- End Method validate_status_webhook_authorization

    def get_webhook_handlers(self) -> Dict[str, Callable]:
        return {"/status": self.handle_status_webhook}
    # -- End Method get_webhook_handlers

    def handle_status_webhook(self, request_data: Dict[str, Any]) -> None:
        handle_jira_status_webhook(bot=self.bot, cfg=self.cfg, logger=self.logger, payload=request_data)
    # -- End Method handle_status_webhook

    def _canonical_team_ref(self, team_ref: str) -> str:
        return canonical_team_ref(team_ref, self._team_name_by_folded)
    # -- End Method _canonical_team_ref

    def _refresh_team_cache(self) -> None:
        if self._team_name_by_folded:
            return
        if not hasattr(self, "bot"):
            return
        refresh_team_cache(
            self.bot,
            self.api_prefix,
            self.headers,
            self.auth,
            self._team_name_by_folded,
            self._team_id_by_folded,
            self.logger,
        )
    # -- End Method _refresh_team_cache

    def _resolve_email_to_account_id(self, email: str) -> Optional[str]:
        return resolve_email_to_account_id_impl(email, self.bot, self.site_api_prefix, self.auth)
    # -- End Method _resolve_email_to_account_id

    def _resolve_config_responders(self) -> RespondersList:
        """Resolve Jira plugin config responders into a typed RespondersList."""
        self._refresh_team_cache()
        lookup = getattr(self.bot, "lookup_plugin", None)
        if lookup is None:
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

    def _resolve_alert_responders(self) -> RespondersList:
        """
        Resolve responders used for Jira alert payloads.

        Jira `responders` config is authoritative when non-empty. When empty, fall back
        to the bot's room responder list.
        """
        refs = list(getattr(self.cfg, "responders", []))
        if refs:
            return self._resolve_config_responders()
        return getattr(self.bot, "responders", RespondersList())
    # -- End Method _resolve_alert_responders

    def _enrich_team_alert_ids(self, responders: RespondersList) -> RespondersList:
        """Fill missing `ThaumTeam.alert_id` values from Jira team cache."""
        self._refresh_team_cache()
        enriched = RespondersList(people=list(responders.people), teams=list(responders.teams))
        for team in enriched.teams:
            if getattr(team, "alert_id", None):
                continue
            folded = str(getattr(team, "team_name", "")).strip().casefold()
            if folded:
                team_id = self._team_id_by_folded.get(folded)
                if team_id:
                    team.alert_id = team_id
        return enriched
    # -- End Method _enrich_team_alert_ids

    def _responders_list_to_jira_payload(self, responders: RespondersList) -> list[dict[str, str]]:
        return responders_list_to_jira_payload(
            responders,
            self._resolve_email_to_account_id,
            self.logger,
        )
    # -- End Method _responders_list_to_jira_payload

    def validate_connection(self) -> bool:
        """Verify we can read team list and resolve responder references."""
        try:
            self._refresh_team_cache()
            responders = self._resolve_alert_responders()
            _ = self._responders_list_to_jira_payload(self._enrich_team_alert_ids(responders))
            return True
        except Exception as e:
            self.logger.error("Jira connection/resolve validation failed: %s", e)
            if self.logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(
                    self.logger,
                    "validate_connection traceback",
                    traceback.format_exc(),
                    LogLevel.SPAM,
                )
            return False
    # -- End Method validate_connection

    def trigger_alert(
        self,
        summary: str,
        room_id: str,
        sender: ThaumPerson,
        priority=AlertPriority.NORMAL,
    ) -> tuple[str, Optional[str]]:
        short_id = self._generate_short_id(4)
        url = f"{self.api_prefix}/v1/alerts"

        responders_typed = self._resolve_alert_responders()
        responders_typed = self._enrich_team_alert_ids(responders_typed)
        responders_payload = self._responders_list_to_jira_payload(responders_typed)

        bk = str(getattr(self.bot, "bot_key", None) or "")
        alert = build_trigger_alert_body(
            summary,
            self.bot.name,
            room_id,
            sender,
            priority,
            self.cfg.priority_normal,
            self.cfg.priority_high,
            short_id,
            responders_payload,
            bk,
            self.bot.plugin_name,
        )

        response = post_alert(url, alert, self.headers, self.auth)
        # #region agent log
        try:
            _req_body = json.dumps(alert, default=str)
            _parsed: Any = None
            try:
                _parsed = response.json()
            except Exception:
                pass
            _log = {
                "sessionId": "d2aafe",
                "runId": "pre-fix",
                "hypothesisId": "A-E",
                "location": "alerts/plugins/jira/plugin.py:trigger_alert",
                "message": "Jira POST /v1/alerts request and response",
                "data": {
                    "url": url,
                    "http_status": response.status_code,
                    "request_body": _req_body[:50000],
                    "response_json": _parsed,
                    "response_text": (response.text or "")[:50000] if _parsed is None else None,
                },
                "timestamp": int(time.time() * 1000),
            }
            _log_path = Path(__file__).resolve().parents[3] / "debug-d2aafe.log"
            with open(_log_path, "a", encoding="utf-8") as _dbg:
                _dbg.write(json.dumps(_log, default=str) + "\n")
        except Exception:
            pass
        # #endregion
        response.raise_for_status()

        alias = str(alert.get("alias") or "")
        upsert_pending_row(short_id, room_id, bk, alias, self.logger)

        self.logger.log(
            LogLevel.VERBOSE,
            "Jira alert accepted: severity=%s alias=%s responders=%d",
            alert["priority"],
            alias,
            len(responders_payload),
        )
        return short_id, alias or None
    # -- End Method trigger_alert
# -- End Class JiraPlugin
