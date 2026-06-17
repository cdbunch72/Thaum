# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# bots/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
import logging
from typing import List, Optional, Tuple, Callable, Dict, Any, Protocol, TYPE_CHECKING, Union
from thaum.types import ThaumPerson, RespondersList, ResolvedStringList
from dataclasses import dataclass, field
from pydantic import BaseModel, model_validator
import re

if TYPE_CHECKING:
    from flask import Request as FlaskRequest

@dataclass
class MessageContext:
    """Canonical message envelope passed to every ``hears()`` handler.

    Attributes:
        room_id: Platform room or space identifier.
        person: Resolved sender as a :class:`thaum.types.ThaumPerson`.
        message: Plain-text message body.
        message_id: Platform-specific message identifier.
        raw_event: Original platform event payload for driver-specific use.
    """
    room_id: str
    person: ThaumPerson
    message: str
    message_id: str
    raw_event: Dict[str,Any] = field(default_factory=dict)

class BotHearsHandler(Protocol):
    """Callable signature for methods registered with :meth:`BaseChatBot.hears`.

    Args:
        bot: The chat bot instance handling the message.
        ctx: Parsed message context.
        match: Regex match object from the registered pattern.
    """

    def __call__(self, bot: 'BaseChatBot', ctx: MessageContext, match: re.Match) -> None: ...

class BaseChatBot(ABC):
    """Abstract base contract for all Thaum chat bot drivers.

    Platform-specific drivers (Webex, Teams, Slack, etc.) must implement the
    abstract messaging, room, identity, and webhook methods defined here.

    Attributes:
        plugin_name: Short plugin key used in platform id maps (e.g. ``"webex"``).
    """
    
    plugin_name: str = 'base'

    def __init__(self, config: 'BaseChatBotConfig'):
        """Initialize bot state from validated configuration.

        Args:
            config: Parsed bot settings from ``[[bots]]`` in TOML.
        """
        self.handle = config.handle
        self.logger = logging.getLogger(f"bot.{self.handle}")
        # Some identity/team flows expect a `.log` attribute for warnings.
        self.log = self.logger
        self.send_alerts = config.send_alerts
        self.high_pri_on = config.high_pri_on
        self.alert_type = config.alert_type
        self.responder_refs = list(config.responders)
        self.responders = RespondersList()
        self.team_description = config.team_description
        self.room_title_template = config.room_title_template
        self.customer_service_message_template = config.customer_service_message_template
        self.incident_prompt_card_template = config.incident_prompt_card_template
        self.incident_prompt_card_template_path = config.incident_prompt_card_template_path
        self.emergency_warning_message = config.emergency_warning_message
        # Set by the server bootstrap code; shared by all bots on a server.
        self.lookup_plugin: Optional[Any] = None
        # Configured in thaum.factory.initialize_bots: TOML bot id for /bot/<bot_key> routing.
        self.bot_key: Optional[str] = None
        self.endpoint = config.endpoint
        # Initialize state here
        self._hears_routes: List[Tuple[int, re.Pattern, Callable]] = []
        self._action_callbacks: List[Callable] = []
    # -- End Method __init__

    @abstractmethod
    def say(self, room_id: str, text: str, markdown: Optional[str] = None) -> None:
        """Send a text message to a room.

        Args:
            room_id: Target room identifier.
            text: Plain-text fallback body.
            markdown: Optional platform-specific markdown; when omitted, ``text`` is used.
        """
        pass
    # -- End Method say

    @abstractmethod
    def send_card(self, room_id: str, card_content: dict, fallback_text: str) -> None:
        """Send an Adaptive Card (or platform equivalent) to a room.

        Args:
            room_id: Target room identifier.
            card_content: Structured card payload for the platform API.
            fallback_text: Plain-text message when the client cannot render the card.
        """
        pass
    # -- End Method send_card

    @abstractmethod
    def create_room(self, title: str) -> str:
        """Create a new chat room.

        Args:
            title: Display title for the new room.

        Returns:
            Platform room identifier for the created room.
        """
        pass
    # -- End Method create_room

    def room_title(self, room_id: str) -> str:
        """Return a room's display title.

        Args:
            room_id: Platform room identifier.

        Returns:
            Human-readable room title, or ``room_id`` when the title is unknown.
        """
        return room_id
    # -- End Method room_title

    @abstractmethod
    def add_members(self, room_id: str, members: List[ThaumPerson]) -> None:
        """Add people to an existing room.

        Args:
            room_id: Target room identifier.
            members: People to invite or add to the room.
        """
        pass
    # -- End Method add_members

    @abstractmethod
    def delete_room(self, room_id: str, person: ThaumPerson) -> None:
        """Permanently remove or archive a room.

        Args:
            room_id: Room to delete.
            person: Person initiating deletion (for audit or platform requirements).
        """
        pass
    # -- End Method delete_room

    def delete_message(self, message_id: str) -> None:
        """Remove a chat message by platform id.

        Default no-op. Override to delete Adaptive Card messages or similar.

        Args:
            message_id: Platform-specific message identifier.
        """
        return
    # -- End Method delete_message

    @abstractmethod
    def get_person(self, person_id: str) -> ThaumPerson:
        """Resolve a platform person id to a :class:`thaum.types.ThaumPerson`.

        Args:
            person_id: Native person identifier for this bot's ``plugin_name``.

        Returns:
            Resolved person record for the given platform id.
        """
        pass
    # -- End Method get_person

    def format_mention(self, person_or_id: Union[ThaumPerson, str, None]) -> str:
        """Format a platform @-mention token for markdown messages.

        Accepts a :class:`thaum.types.ThaumPerson` or a native chat ``person_id``
        string for this bot's ``plugin_name``. Returns plain display text when
        mentions are unsupported.

        Args:
            person_or_id: Person object, platform person id, or ``None``.

        Returns:
            Mention markdown for the platform, display name fallback, or empty
            string when ``person_or_id`` is ``None``.
        """
        if person_or_id is None:
            return ""
        if isinstance(person_or_id, ThaumPerson):
            pid = person_or_id.platform_ids.get(self.plugin_name)
            if pid:
                return self._mention_markdown_for_person_id(pid)
            return person_or_id.for_display
        s = str(person_or_id).strip()
        if not s:
            return ""
        return self._mention_markdown_for_person_id(s)
    # -- End Method format_mention

    def _mention_markdown_for_person_id(self, person_id: str) -> str:
        """Override in drivers that support @-mentions in ``say(..., markdown=True)``."""
        return person_id
    # -- End Method _mention_markdown_for_person_id

    @abstractmethod
    def handle_event(self, event: Dict[str, Any]) -> None:
        """Process an inbound platform webhook event.

        Args:
            event: Parsed event payload from the chat platform.
        """
        pass
    # -- End Method handle_event

    @abstractmethod
    def authenticate_request(self, request: "FlaskRequest") -> bool:
        """Verify an incoming webhook request before processing.

        Subclasses should extract required auth material from the request
        (headers, raw body, signatures, etc.) and return True on success.

        Args:
            request: Flask request object for the inbound webhook.

        Returns:
            True when the request is authentic; False otherwise.
        """
        pass
    # -- End Method authenticate_request

    @abstractmethod
    def register_bot_webhook(self) -> None:
        """Register inbound webhooks with the chat platform.

        Called after HTTP routes are live (e.g. ``POST .../bot/<bot_key>``).
        Default no-op; some drivers register webhooks from the leader maintenance
        loop instead.
        """
        return
    # -- End Method register_bot_webhook

    def hears(self, pattern: str, priority: int=50):
        """Register a regex pattern handler for incoming messages.

        Args:
            pattern: Case-insensitive regex matched against message text.
            priority: Lower values run first when multiple patterns match (default 50).

        Returns:
            Decorator that registers a :class:`BotHearsHandler` on this bot.
        """
        def decorator(handler: BotHearsHandler):
            self._hears_routes.append((priority,re.compile(pattern, re.IGNORECASE), handler))
            self._hears_routes.sort(key=lambda x: x[0])
            return handler
        return decorator

    def on_action(self, handler):
        """Register a callback for Adaptive Card action submissions.

        Args:
            handler: Callable invoked when a card action is received.

        Returns:
            The same ``handler`` (allows use as a decorator).
        """
        self._action_callbacks.append(handler)
        return handler
# -- End Class BaseChatBot

class BaseChatBotConfig(BaseModel):
    """Configuration model for a single bot entry under ``[[bots]]`` in TOML.

    Attributes:
        handle: Web-style **mention** identifier for this bot (e.g. Webex Bot
            username); used for logging context, not display.
        endpoint: Public HTTPS URL for this bot's inbound events (factory default:
            ``{base_url}/bot/{bot_key}``).
        high_pri_on: When True, high-priority alert flows are enabled.
        send_alerts: When True, alerts are sent via the configured ``alert_type``.
        responders: Responder references resolved at startup (emails, teams, etc.).
        room_title_template: Jinja template for incident room titles.
        customer_service_message_template: Message posted while responders are paged.
        incident_prompt_card_template: Inline Adaptive Card template JSON.
        incident_prompt_card_template_path: Filesystem path to card template JSON.
        alert_type: Alert plugin module name under ``alerts.plugins``; use ``"null"``
            when ``send_alerts`` is False.
        team_description: Human-readable team name used in templates and alerts.
        emergency_warning_message: Optional warning shown for emergency incidents.
    """

    handle: str
    # Public HTTPS URL for this bot's events (factory default: ``{base_url}/bot/{bot_key}``).
    endpoint: str
    high_pri_on: Optional[bool] = True
    send_alerts: Optional[bool] = True
    responders: ResolvedStringList
    room_title_template: Optional[str] = '{{requester_name}} - {{team_description}} {{date}}'
    customer_service_message_template: Optional[str] = (
        "Thank you for your patience.  The next available person from "
        "{{ team_description }} will be with you shortly."
    )
    incident_prompt_card_template: Optional[str] = None
    incident_prompt_card_template_path: Optional[str] = None
    # Alert plugin module name under ``alerts.plugins``; use ``null`` when send_alerts is False.
    alert_type: str = "null"
    team_description: str
    emergency_warning_message: Optional[str]

    @model_validator(mode='after')
    def consistent_alert_settings(self) -> "BaseChatBotConfig":
        """Enforce consistent ``send_alerts``, ``alert_type``, and ``high_pri_on`` values.

        Returns:
            This config instance when validation passes.

        Raises:
            ValueError: When alert-related fields are mutually inconsistent.
        """
        if self.send_alerts and self.alert_type == "null":
            raise ValueError(
                f"{self.handle}: send_alerts=True requires alert_type other than 'null'."
            )

        if not self.send_alerts and self.alert_type != "null":
            raise ValueError(
                f"{self.handle}: send_alerts=False requires alert_type='null'."
            )

        if self.high_pri_on:
            if not self.send_alerts:
                raise ValueError(
                    f"{self.handle}: high_pri_on=True requires send_alerts to also be True."
                )

        return self
    # -- End consistent_alert_settings
