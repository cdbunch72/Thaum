# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# bots/plugins/webex_bot.py
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlsplit, urlunsplit
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple

from pydantic import Field, model_validator

from bots.base import BaseChatBot, BaseChatBotConfig, MessageContext
from log_setup import log_debug_blob
from thaum.types import LogLevel, ResolvedSecret, ServerConfig, ThaumPerson
from webexpythonsdk import WebexAPI

if TYPE_CHECKING:
    from flask import Request as FlaskRequest


MIN_HMAC_SECRET_CHARS: int = 16

WebexHmacMode = Literal["shared_db", "pinned", "disabled"]


def _me_email_addresses(me: Any) -> Tuple[str, ...]:
    """Normalize Webex Person ``emails`` into plain address strings."""
    raw = getattr(me, "emails", None) or []
    addrs: List[str] = []
    for item in raw:
        if isinstance(item, str):
            s = item.strip()
        elif isinstance(item, dict):
            s = str(item.get("value") or "").strip()
        else:
            v = getattr(item, "value", None)
            s = str(v).strip() if v is not None else ""
        if s and "@" in s:
            addrs.append(s)
    return tuple(addrs)


def strip_webex_self_mentions(text: str, person_id: str, emails: Tuple[str, ...]) -> str:
    """
    Remove @-mention markup for this bot from Webex message text.

    Webex uses ``<@personId:ID>`` and often ``<@personId:ID|Display Name>``; the
    plain ``replace`` of the short form leaves ``|Name>`` and breaks command regexes.
    """
    cleaned = text
    if person_id:
        cleaned = re.sub(
            rf"<@personId:{re.escape(person_id)}(?:\|[^>]*)?>",
            "",
            cleaned,
        )
    for em in emails:
        cleaned = re.sub(
            rf"(?i)<@personEmail:{re.escape(em)}(?:\|[^>]*)?>",
            "",
            cleaned,
        )
    return cleaned.strip()


def strip_leading_bot_labels(text: str, *labels: str) -> str:
    """
    Remove a leading plaintext bot label left after Webex expands @mentions in ``text``.

    ``message.text`` often begins with the bot display name (e.g. ``askDBA``) while
    ``markdown`` carries ``<@personId:…>``; if only ``text`` is used, command regexes
    never see ``implode`` / ``usage`` at ``^`` and the unknown handler treats the name
    as the command token.
    """
    s = text.strip()
    seen_lower: set[str] = set()
    for label in labels:
        label = (label or "").strip()
        if len(label) < 2:
            continue
        low = label.lower()
        if low in seen_lower:
            continue
        seen_lower.add(low)
        s = re.sub(rf"(?i)^{re.escape(label)}\s+", "", s)
    return s.strip()


class WebexChatBot(BaseChatBot):
    """Concrete driver for Webex."""

    plugin_name: str = "webex"

    def __init__(self, config: WebexChatBotConfig):
        super().__init__(config)
        self.logger = logging.getLogger(f"bot.{config.name}")
        self.log = self.logger
        self._web_cfg = config
        self.hmac_mode: WebexHmacMode = config.hmac_mode
        self.api = WebexAPI(access_token=config.token.get_secret_value())
        self.me = self.api.people.me()

        if config.hmac_mode == "pinned":
            self.hmac_secret = (
                config.hmac_secret.get_secret_value() if config.hmac_secret else None
            )
        else:
            self.hmac_secret = None

        self._hmac_cache_plain: Optional[str] = None
        self._hmac_cache_monotonic: float = 0.0
        self._webhook_ids: Optional[tuple[str, ...]] = None
        # First probe must not be delayed until `webhook_probe_interval_seconds` elapses; monotonic
        # time 0 is only ~seconds after boot, so initializing to 0 incorrectly throttles registration.
        self._last_probe_monotonic: float = float("-inf")
        self._hears_routes = []

    def complete_runtime_init(self, server_cfg: ServerConfig) -> None:
        """Load shared DB HMAC after ``bot_key`` is set (requires database crypto)."""
        if self.hmac_mode != "shared_db":
            return
        from thaum.bot_webhook_state import ensure_bot_webhook_hmac_secret
        from thaum.database_crypto import is_database_crypto_ready

        if not is_database_crypto_ready():
            raise RuntimeError(
                "server.database.database_vault_passphrase / database crypto is required when "
                "Webex hmac_secret is omitted (shared DB HMAC mode)."
            )
        bk = self.bot_key
        if not bk:
            raise RuntimeError("bot_key must be set before complete_runtime_init()")
        secret = ensure_bot_webhook_hmac_secret(bk, min_length=MIN_HMAC_SECRET_CHARS)
        self.hmac_secret = secret
        self._hmac_cache_plain = secret
        self._hmac_cache_monotonic = time.monotonic()

    def _effective_hmac_secret(self) -> Optional[str]:
        if self.hmac_mode == "disabled":
            return None
        if self.hmac_mode == "pinned":
            return self.hmac_secret
        now = time.monotonic()
        refresh = float(self._web_cfg.webhook_hmac_cache_refresh_seconds)
        bk = self.bot_key or ""
        if self._hmac_cache_plain is None or (now - self._hmac_cache_monotonic) >= refresh:
            from thaum.bot_webhook_state import ensure_bot_webhook_hmac_secret

            self._hmac_cache_plain = ensure_bot_webhook_hmac_secret(
                bk, min_length=MIN_HMAC_SECRET_CHARS
            )
            self._hmac_cache_monotonic = now
        return self._hmac_cache_plain

    def _normalize_target_url(self, url: str) -> str:
        return url.rstrip("/")

    def _normalize_target_url_for_prune(self, url: str) -> str:
        """
        Canonicalize webhook target for cleanup matching.

        Pruning treats HTTP and HTTPS variants as the same endpoint so a
        protocol migration does not leave stale hooks behind.
        """
        normalized = self._normalize_target_url(url)
        parts = urlsplit(normalized)
        if not parts.netloc:
            return normalized
        return urlunsplit(("", parts.netloc, parts.path, parts.query, ""))

    def _webhook_secret_for_api(self) -> Optional[str]:
        return self._effective_hmac_secret()

    def register_bot_webhook(self) -> None:
        target = (self.endpoint or "").strip()
        if not target:
            self.logger.error("Cannot register Webex webhooks: bot endpoint is not configured.")
            return

        nt = self._normalize_target_url_for_prune(target)
        try:
            existing = list(self.api.webhooks.list())
            for wh in existing:
                if wh.targetUrl and self._normalize_target_url_for_prune(wh.targetUrl) == nt:
                    self.api.webhooks.delete(wh.id)
        except Exception as e:
            self.logger.warning("While pruning old Webex webhooks: %s", e)

        secret = self._webhook_secret_for_api()
        name_prefix = f"Thaum {self.name}"
        if self.bot_key:
            name_prefix = f"{name_prefix} [{self.bot_key}]"

        try:
            w1 = self.api.webhooks.create(
                name=f"{name_prefix} messages",
                targetUrl=target,
                resource="messages",
                event="created",
                secret=secret,
            )
            w2 = self.api.webhooks.create(
                name=f"{name_prefix} attachmentActions",
                targetUrl=target,
                resource="attachmentActions",
                event="created",
                secret=secret,
            )
            self._webhook_ids = (w1.id, w2.id)
            self.logger.log(
                LogLevel.VERBOSE,
                "Ensured Webex webhooks for bot_key=%r -> %s",
                self.bot_key,
                target,
            )
        except Exception as e:
            self.logger.error("Failed to register Webex webhooks: %s", e)
            raise

    def _fetch_webhook(self, wid: str) -> Any:
        get_fn = getattr(self.api.webhooks, "get", None)
        if callable(get_fn):
            try:
                return get_fn(wid)
            except TypeError:
                return get_fn(webhookId=wid)
        for wh in self.api.webhooks.list():
            if wh.id == wid:
                return wh
        return None

    def _probe_webhook_status(self) -> None:
        now = time.monotonic()
        _interval = float(self._web_cfg.webhook_probe_interval_seconds)
        _elapsed = now - self._last_probe_monotonic
        if _elapsed < _interval:
            return
        self._last_probe_monotonic = now

        target = (self.endpoint or "").strip()
        if not target:
            return

        ids = self._webhook_ids
        if not ids:
            self.register_bot_webhook()
            return

        for wid in ids:
            try:
                wh = self._fetch_webhook(wid)
                if wh is None:
                    raise ValueError("missing webhook")
                status = getattr(wh, "status", None)
                wh_target = getattr(wh, "targetUrl", None)
                if wh_target and self._normalize_target_url(str(wh_target)) != self._normalize_target_url(target):
                    raise ValueError("target_mismatch")
                if status is not None and str(status).lower() != "active":
                    raise ValueError("inactive")
            except Exception as e:
                self.logger.info("Webex webhook probe failed for %s; reconciling. reason=%s", wid, e)
                self._webhook_ids = None
                self.register_bot_webhook()
                return

    def _leader_maintenance_tick(self) -> None:
        if not (self.endpoint or "").strip():
            return
        self._probe_webhook_status()

    def say(self, room_id: str, text: str, markdown: Optional[str] = None) -> None:
        self.api.messages.create(roomId=room_id, text=text, markdown=markdown)
    # -- End Method say

    def send_card(
        self, room_id: str, card_content: dict, fallback_text: str = "Adaptive Card"
    ) -> None:
        attachment = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card_content,
        }
        self.api.messages.create(
            roomId=room_id, text=fallback_text, attachments=[attachment]
        )

    def delete_message(self, message_id: str) -> None:
        try:
            self.api.messages.delete(message_id)
        except Exception as e:
            self.logger.error("Failed to delete message %s: %s", message_id, e)

    def create_room(self, title: str) -> str:
        room = self.api.rooms.create(title=title)
        return room.id
    # -- End Method create_room

    def add_members(self, room_id: str, members: List[ThaumPerson]) -> None:
        for m in members:
            pid = m.platform_ids.get(self.plugin_name)
            if pid:
                key, v = "personId", pid
            else:
                key, v = "personEmail", m.email

            try:
                self.api.memberships.create(roomId=room_id, **{key: v})
            except Exception as e:
                self.logger.error(f"Failed to add {m} to {room_id}: {e}")
    # -- End Method add_members

    def delete_room(self, room_id: str, person: Optional[ThaumPerson] = None) -> None:
        display_name = person.for_display if person else "An unknown user"

        try:
            room = self.api.rooms.get(room_id)

            if room.creatorId != self.me.id:
                self.logger.warning(
                    f"Unauthorized attempt to delete room '{room.title}' by {display_name}"
                )
                self.say(
                    room_id,
                    f"Access Denied: {self.name} did not create room '{room.title}'",
                )
                return

            self.api.rooms.delete(room_id)
            self.logger.log(
                LogLevel.VERBOSE,
                "Room %s deleted by %s.",
                room_id,
                display_name,
            )

        except Exception as e:
            self.logger.error(f"Catastrophic failure deleting {room_id}: {e}")
            self.say(room_id, "Critical failure during room deletion.")

    def _get_person_from_api(self, person_id: str) -> ThaumPerson:
        try:
            person = self.api.people.get(person_id)
            email = person.emails[0] if person.emails else None
            if not email:
                self.logger.warning(
                    f"Webex person {person_id} has no email. Using ID as fallback."
                )
                email = f"{person_id}@{self.plugin_name}"

            return ThaumPerson(
                email=email,
                display_name=person.displayName,
                platform_ids={self.plugin_name: person_id},
                source_plugin=self.plugin_name,
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch person {person_id} from Webex: {e}")
            return ThaumPerson(
                email=f"{person_id}@{self.plugin_name}",
                display_name="",
                platform_ids={self.plugin_name: person_id},
                source_plugin=self.plugin_name,
            )

    def get_person(self, person_id) -> ThaumPerson:
        lookup = getattr(self, "lookup_plugin", None)
        if lookup is not None:
            cached = lookup.get_person_by_id(self.plugin_name, person_id)
            if cached is not None:
                return cached

        fragment = self._get_person_from_api(person_id)
        if lookup is not None:
            return lookup.merge_person(fragment)
        return fragment

    def format_mention(self, person_or_id: ThaumPerson | str | None) -> str:
        if person_or_id is None:
            return ""
        if isinstance(person_or_id, ThaumPerson):
            pid = person_or_id.platform_ids.get(self.plugin_name)
            if not pid:
                lookup = getattr(self, "lookup_plugin", None)
                if lookup is not None:
                    try:
                        resolved = lookup.get_person_by_email(person_or_id.email)
                    except Exception:
                        resolved = None
                    if resolved is not None:
                        pid = resolved.platform_ids.get(self.plugin_name)
            if pid:
                return f"<@personId:{pid}>"
            return (person_or_id.display_name or "").strip() or person_or_id.email
        s = str(person_or_id).strip()
        return f"<@personId:{s}>" if s else ""

    def _validate_signature(self, payload_body: bytes, signature: Optional[str]) -> bool:
        secret = self._effective_hmac_secret()
        if not secret:
            return True
        if not signature:
            return False

        import hashlib
        import hmac

        hashed = hmac.new(secret.encode(), payload_body, hashlib.sha1)
        return hmac.compare_digest(hashed.hexdigest(), signature)

    def authenticate_request(self, request: "FlaskRequest") -> bool:
        try:
            raw_body = request.get_data(cache=True)  # type: ignore[attr-defined]
        except Exception:
            raw_body = getattr(request, "data", b"") or b""

        signature = None
        try:
            signature = request.headers.get("X-Spark-Signature")  # type: ignore[attr-defined]
        except Exception:
            signature = None

        return self._validate_signature(raw_body, signature)

    def _process_message(self, message_id: str) -> Optional[str]:
        message = self.api.messages.get(message_id)
        room = self.api.rooms.get(message.roomId)
        is_direct = room.type == "direct"
        is_mentioned = message.mentionedPeople and self.me.id in message.mentionedPeople

        if not (is_direct or is_mentioned):
            return None

        md = getattr(message, "markdown", None)
        tx = (message.text or "").strip()
        raw = (md.strip() if isinstance(md, str) and md.strip() else "") or tx
        if not raw:
            return None

        clean_text = strip_webex_self_mentions(
            raw,
            self.me.id,
            _me_email_addresses(self.me),
        )
        clean_text = strip_leading_bot_labels(
            clean_text,
            self.name,
            (getattr(self.me, "displayName", None) or "").strip(),
            (getattr(self, "bot_key", None) or "").strip(),
        )
        return clean_text if clean_text else None
# -- End Method process_message

    def handle_event(self, event: Dict[str, Any]) -> None:
        resource: Optional[str] = event.get("resource")
        data: Dict[str, Any] = event.get("data", {})
        self.logger.log(LogLevel.SPAM, "handle_event:")
        log_debug_blob(self.logger, "handle_event", data, LogLevel.SPAM)

        if resource == "messages":
            if data.get("personId") == self.me.id:
                return

            clean_text = self._process_message(data["id"])
            if clean_text is None:
                self.logger.debug(
                    "Ignoring Webex message (not a DM and bot not @mentioned); room_id=%s message_id=%s",
                    data.get("roomId"),
                    data.get("id"),
                )
                return

            person = self.get_person(data["personId"])
            message = MessageContext(
                room_id=data["roomId"],
                person=person,
                message=clean_text,
                message_id=data["id"],
                raw_event=event,
            )
            for _priority, pattern, handler in self._hears_routes:
                match = pattern.search(clean_text)
                if match:
                    handler(self, message, match)
                    break

        elif resource == "attachmentActions":
            action = self.api.attachment_actions.get(data["id"])
            for callback in self._action_callbacks:
                callback(self, action)


class WebexChatBotConfig(BaseChatBotConfig):
    token: ResolvedSecret
    hmac_mode: WebexHmacMode = Field(
        default="shared_db",
        description="How webhook HMAC is sourced: shared_db (omit hmac_secret), pinned, or disabled.",
    )
    hmac_secret: Optional[ResolvedSecret] = Field(
        default=None,
        description="Pinned signing secret; leave unset with shared_db mode (DB-stored secret).",
    )
    webhook_hmac_cache_refresh_seconds: float = Field(
        default=30.0,
        ge=0.0,
        description="How often workers reload the shared HMAC plaintext from the DB.",
    )
    webhook_probe_interval_seconds: float = Field(
        default=3600.0,
        ge=1.0,
        description="Leader: minimum seconds between Webex webhook status probes.",
    )

    @model_validator(mode="before")
    @classmethod
    def _classify_hmac(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "hmac_mode" in out:
            return out
        if "hmac_secret" not in out:
            out["hmac_mode"] = "shared_db"
            return out
        raw = out.get("hmac_secret")
        if raw is None:
            out["hmac_mode"] = "disabled"
            out["hmac_secret"] = None
            return out
        s = str(raw).strip()
        if not s:
            out["hmac_mode"] = "disabled"
            out["hmac_secret"] = None
            return out
        out["hmac_mode"] = "pinned"
        return out

    @model_validator(mode="after")
    def _validate_hmac(self) -> WebexChatBotConfig:
        if self.hmac_mode == "pinned":
            if self.hmac_secret is None:
                raise ValueError("hmac_mode=pinned requires a non-empty hmac_secret")
            s = self.hmac_secret.get_secret_value().strip()
            if len(s) < MIN_HMAC_SECRET_CHARS:
                raise ValueError(
                    f"hmac_secret is too short; must be >= {MIN_HMAC_SECRET_CHARS} characters"
                )
        elif self.hmac_mode == "shared_db":
            self.hmac_secret = None
        else:
            self.hmac_secret = None
        return self


def maintenance_tasks_register(registry: Any, *, server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    expected_bot_type = __name__.rsplit(".", 1)[-1]
    allowed_bot_types = {expected_bot_type, "webex"}
    if server_cfg.bot_type not in allowed_bot_types:
        return
    interval = 3600.0
    for row in (config.get("bots") or {}).values():
        if not isinstance(row, dict):
            continue
        vb = row.get("_validated_bot")
        probe = getattr(vb, "webhook_probe_interval_seconds", None)
        if probe is not None:
            try:
                interval = min(interval, float(probe))
            except (TypeError, ValueError):
                raise

    def _tick(ctx: Any, _task_data: Any) -> None:
        for bot in ctx["bots"].values():
            if getattr(bot, "plugin_name", None) == "webex":
                bot._leader_maintenance_tick()

    tick_interval = max(60.0, interval)
    logging.getLogger(__name__).log(
        LogLevel.VERBOSE,
        "Leader maintenance: registered webex_webhook_maintenance every %.1f s "
        "(run_on_startup=True; leader also runs on tick when ids missing or probe fails)",
        tick_interval,
    )
    registry.register_task(
        "webex_webhook_maintenance",
        tick_interval,
        _tick,
        run_on_startup=True,
    )


def get_config_model():
    return WebexChatBotConfig


def create_instance_bot(config: WebexChatBotConfig) -> WebexChatBot:
    return WebexChatBot(config)