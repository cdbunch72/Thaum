# bots/plugins/webex_bot.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations
import logging
import secrets
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from pydantic import Field, SecretStr, model_validator
from thaum.types import LogLevel, ResolvedSecret, ThaumPerson
from webexpythonsdk import WebexAPI
from bots.base import BaseChatBot, MessageContext, BaseChatBotConfig
from log_setup import log_debug_blob

if TYPE_CHECKING:
    from flask import Request as FlaskRequest


# Minimum HMAC secret length to avoid accidental weak configuration.
# Webex accepts arbitrary secrets, but we enforce a lower bound for safety.
MIN_HMAC_SECRET_CHARS: int = 16


class WebexChatBot(BaseChatBot):
    """Concrete driver for Webex."""

    plugin_name: str = 'webex'

    def __init__(self, config: 'WebexChatBotConfig'):
        super().__init__(config)
        self.logger = logging.getLogger(f"bot.{config.name}")
        self.log = self.logger
        self.api = WebexAPI(access_token=config.token.get_secret_value())
        self.me = self.api.people.me()
        self.hmac_secret = (
            None
            if config.hmac_secret is None
            else config.hmac_secret.get_secret_value()
        )
        
        # Internal state for bot behavior
        self._hears_routes = []
    # -- End Method __init__

    def say(self, room_id: str, text: str, markdown: Optional[str] = None) -> None:
        self.api.messages.create(roomId=room_id, text=text, markdown=markdown)
    # -- End Method say

    def send_card(self, room_id: str, card_content: dict, fallback_text: str = "Adaptive Card") -> None:
        attachment = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card_content
        }
        self.api.messages.create(roomId=room_id, text=fallback_text, attachments=[attachment])
    # -- End Method send_card

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
        """Implodes the room ONLY if bot is the creator."""
        display_name = person.for_display if person else "An unknown user"
        
        try:
            room = self.api.rooms.get(room_id)
            
            if room.creatorId != self.me.id:
                self.logger.warning(f"Unauthorized attempt to delete room '{room.title}' by {display_name}")
                self.say(room_id, f"Access Denied: {self.name} did not create room '{room.title}'")
                return # Stop here, don't crash the server
                
            self.api.rooms.delete(room_id)
            self.logger.verbose(f"Room {room_id} deleted by {display_name}.")
            
        except Exception as e:
            # Here is the only place you actually need an exception handler
            self.logger.error(f"Catastrophic failure deleting {room_id}: {e}")
            self.say(room_id, "Critical failure during room deletion.")

    # -- End Method delete_room


    def _get_person_from_api(self, person_id: str) -> ThaumPerson:
        """
        Fetches a person from the Webex API and returns a ThaumPerson.
        """
        try:
            # 1. Fetch the person object
            person = self.api.people.get(person_id)
            
            # 2. Extract the canonical email (take the first one if multiple exist)
            email = person.emails[0] if person.emails else None
            
            # 3. Handle cases where API might not return an email (rare but possible)
            if not email:
                self.logger.warning(f"Webex person {person_id} has no email. Using ID as fallback.")
                email = f"{person_id}@{self.plugin_name}"
                
            # 4. Map to ThaumPerson
            return ThaumPerson(
                email=email,
                display_name=person.displayName,
                platform_ids={self.plugin_name: person_id},
                source_plugin=self.plugin_name # e.g., 'webex_bot'
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch person {person_id} from Webex: {e}")
            # Return a 'placeholder' person so the system doesn't crash
            return ThaumPerson(
                email=f"{person_id}@{self.plugin_name}",
                display_name="",
                platform_ids={self.plugin_name: person_id},
                source_plugin=self.plugin_name,
            )
    # -- End Method get_person_from_api

    def get_person(self,person_id) -> ThaumPerson:
        lookup = getattr(self, "lookup_plugin", None)
        if lookup is not None:
            cached = lookup.get_person_by_id(self.plugin_name, person_id)
            if cached is not None:
                return cached

        # Cache miss (or lookup plugin not attached): resolve via Webex API,
        # then merge/cache the partial object by email.
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
    # -- End Method format_mention

    def _validate_signature(self, payload_body: bytes, signature: Optional[str]) -> bool:
        """Return True if the request signature is valid.

        If ``hmac_secret`` is unset/disabled (empty in config), signatures are not verified.
        """
        if not self.hmac_secret:
            return True
        if not signature:
            return False

        import hmac, hashlib

        hashed = hmac.new(self.hmac_secret.encode(), payload_body, hashlib.sha1)
        return hmac.compare_digest(hashed.hexdigest(), signature)
    # -- End Method validate_signature

    def authenticate_request(self, request: "FlaskRequest") -> bool:
        """Extract Webex webhook signature + raw body and verify it."""
        try:
            # Flask's `request.get_data()` returns the raw body bytes (and caches them on the request object).
            raw_body = request.get_data(cache=True)  # type: ignore[attr-defined]
        except Exception:
            # Fallback for non-Flask request objects.
            raw_body = getattr(request, "data", b"") or b""

        signature = None
        try:
            signature = request.headers.get("X-Spark-Signature")  # type: ignore[attr-defined]
        except Exception:
            signature = None

        return self._validate_signature(raw_body, signature)
    # -- End Method authenticate_request

    def _process_message(self, message_id: str) -> Optional[str]:
        """
        Fetches the message and returns the clean text ONLY if 
        it's a DM or a mention. Otherwise returns None.
        """
        message = self.api.messages.get(message_id)
        
        # 1. DM Check
        room = self.api.rooms.get(message.roomId)
        is_direct = (room.type == "direct")
        
        # 2. Mention Check
        is_mentioned = message.mentionedPeople and self.me.id in message.mentionedPeople
        
        if not (is_direct or is_mentioned):
            return None # Ignore this message
            
        # 3. Clean the text (strip mention tag)
        if message.text:
            mention_tag = f"<@personId:{self.me.id}>"
            clean_text = message.text.replace(mention_tag, "").strip()
            return clean_text
            
        return None
# -- End Method process_message

    def handle_event(self, event: Dict[str, Any]) -> None:
        """
        Dispatches incoming webhook events.
        'event' is the raw JSON dictionary from the Webex API.
        """
        resource: Optional[str] = event.get('resource')
        data: Dict[str, Any] = event.get('data', {})
        self.logger.spam("handle_event:")
        log_debug_blob(self.logger, data, logging.SPAM)

        if resource == 'messages':
            # Ignore messages sent by the bot itself
            if data.get('personId') == self.me.id: 
                return

            # Fetch the clean text
            clean_text = self._process_message(data['id'])
            if clean_text is None:
                self.logger.debug("Message ignored: Not a DM or Mention.")
                return

            person=self.get_person(data['personId'])
            message=MessageContext(
                room_id=data['roomId'],
                person=person,
                message=clean_text,
                message_id=data['id'],
                raw_event=event
            )
            # Match routes (same tuple shape as BaseChatBot.hears: priority, pattern, handler)
            for _priority, pattern, handler in self._hears_routes:
                match = pattern.search(clean_text)
                if match:
                    handler(self, message, match)
                    break
        # -- End Resource 'messages'

        elif resource == 'attachmentActions':
            action = self.api.attachment_actions.get(data['id'])
            for callback in self._action_callbacks:
                callback(self, action)
        # -- End Resource 'attachmentActions'
    # -- End Method handle_event

    def register_bot_webhook(self) -> None:
        """
        Register Webex webhooks after the Thaum HTTP route for ``self.endpoint`` is live.

        Uses two filtered ``messages`` / ``created`` hooks (both invoke ``handle_event``) to
        cut traffic versus an unfiltered subscription: ``roomType=direct`` (DMs) and
        ``mentionedPeople=me`` (group rooms where the bot is @-mentioned). Also registers
        ``attachmentActions`` / ``created`` for Adaptive Card actions.

        Prunes any existing hooks that use the same ``targetUrl`` (including legacy unfiltered
        message hooks). A DM that also @-mentions the bot may match both filters and deliver
        two events for the same message.
        """
        target = (self.endpoint or "").strip()
        if not target:
            self.logger.error("Cannot register Webex webhooks: bot endpoint is not configured.")
            return

        def _normalize_url(url: str) -> str:
            return url.rstrip("/")

        nt = _normalize_url(target)
        try:
            for wh in list(self.api.webhooks.list()):
                if wh.targetUrl and _normalize_url(wh.targetUrl) == nt:
                    self.api.webhooks.delete(wh.id)
        except Exception as e:
            self.logger.warning("While pruning old Webex webhooks: %s", e)

        secret = self.hmac_secret
        name_prefix = f"Thaum {self.name}"
        if self.bot_key:
            name_prefix = f"{name_prefix} [{self.bot_key}]"

        try:
            self.api.webhooks.create(
                name=f"{name_prefix} messages (direct)",
                targetUrl=target,
                resource="messages",
                event="created",
                filter="roomType=direct",
                secret=secret,
            )
            self.api.webhooks.create(
                name=f"{name_prefix} messages (mentioned)",
                targetUrl=target,
                resource="messages",
                event="created",
                filter="mentionedPeople=me",
                secret=secret,
            )
            self.api.webhooks.create(
                name=f"{name_prefix} attachmentActions",
                targetUrl=target,
                resource="attachmentActions",
                event="created",
                secret=secret,
            )
            self.logger.log(
                LogLevel.VERBOSE,
                "Registered Webex webhooks for bot_key=%r -> %s",
                self.bot_key,
                target,
            )
        except Exception as e:
            self.logger.error("Failed to register Webex webhooks: %s", e)
            raise
    # -- End Method register_bot_webhook
# -- End Class WebexChatBot


class WebexChatBotConfig(BaseChatBotConfig):
    token: ResolvedSecret
    hmac_secret: Optional[ResolvedSecret] = Field(
        default=None,
        description=(
            "Webex webhook signing secret (X-Spark-Signature). If the field is omitted, a "
            "random value is generated at startup (single-process; re-register webhooks after "
            "restart or pin a secret). Set to empty to disable verification. Any other value "
            "is used as-is, but must be at least the minimum length."
        ),
    )

    @model_validator(mode="after")
    def normalize_hmac_secret(self) -> WebexChatBotConfig:
        if self.hmac_secret is not None:
            s = self.hmac_secret.get_secret_value().strip()
            if not s:
                self.hmac_secret = None
                return self
            if len(s) < MIN_HMAC_SECRET_CHARS:
                raise ValueError(
                    f"hmac_secret is too short; must be >= {MIN_HMAC_SECRET_CHARS} characters "
                    f"(or set it to empty to disable verification)."
                )
            # Keep the secret (non-empty, meets minimum length).
            return self

        # Field omitted => generate one for this process.
        # (This is intentionally single-process only, unless you store/pin the generated value.)
        self.hmac_secret = SecretStr(secrets.token_hex(32))
        return self
    # -- End normalize_hmac_secret


def get_config_model():
    return WebexChatBotConfig


def create_instance_bot(config: WebexChatBotConfig) -> WebexChatBot:
    """Factory interface for the Webex driver."""
    return WebexChatBot(config)
# -- End Function create_instance_bot

