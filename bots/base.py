# bots/base.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations
from abc import ABC, abstractmethod
import logging
from typing import List, Optional, Tuple, Callable, Dict, Any, Protocol, TYPE_CHECKING
from thaum.types import ThaumPerson, RespondersList
from dataclasses import dataclass, field
from pydantic import BaseModel, model_validator
import re

if TYPE_CHECKING:
    from flask import Request as FlaskRequest

@dataclass
class MessageContext:
    """The canonical object passed to every hears() handler."""
    room_id: str
    person: ThaumPerson
    message: str
    message_id: str
    raw_event: Dict[str,Any] = field(default_factory=dict)

class BotHearsHandler(Protocol):
    """ Signature for handlers for the hears decorator"""
    def __call__(self, bot: 'BaseChatBot', ctx: MessageContext, match: re.Match) -> None: ...

class BaseChatBot(ABC):
    """
    The Base Contract for all Thaum Bot drivers.
    Any platform-specific driver (Webex, Teams, Slack) must implement these methods.
    """
    
    plugin_name: str = 'base'

    def __init__(self, config: 'BaseChatBotConfig'):
        self.name = config.name
        self.logger = logging.getLogger(f"bot.{self.name}")
        # Some identity/team flows expect a `.log` attribute for warnings.
        self.log = self.logger
        self.send_alerts = config.send_alerts
        self.high_pri_on = config.high_pri_on
        self.alert_type = config.alert_type
        self.responder_refs = list(config.responders)
        self.responders = RespondersList()
        self.team_description = config.team_description
        self.room_title_template = config.room_title_template
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
        """Sends a message to the specified room."""
        pass
    # -- End Method say

    @abstractmethod
    def send_card(self, room_id: str, card_content: dict, fallback_text: str) -> None:
        """Sends an Adaptive Card to the room."""
        pass
    # -- End Method send_card

    @abstractmethod
    def create_room(self, title: str) -> str:
        """Creates a room and returns the room_id."""
        pass
    # -- End Method create_room

    @abstractmethod
    def add_members(self, room_id: str, members: List[ThaumPerson]) -> None:
        """Adds a list of ThaumPeople to the room."""
        pass
    # -- End Method add_members

    @abstractmethod
    def delete_room(self, room_id: str, person: ThaumPerson) -> None:
        """Permanently removes/implodes the room."""
        pass
    # -- End Method delete_room
    
    @abstractmethod
    def get_person(self, person_id: str) -> ThaumPerson:
        """Takes a bot_type-specific person_id and returns a ThaumPerson"""
        pass
    # -- End Method get_person
    
    @abstractmethod
    def handle_event(self, event: Dict[str, Any]) -> None:
        """Called by the bot's webhook route"""
        pass
    # -- End Method handle_event

    @abstractmethod
    def authenticate_request(self, request: "FlaskRequest") -> bool:
        """
        Verify the incoming request before calling `handle_event`.

        Subclasses should extract any required auth material from the request
        (e.g. headers, raw body) and return True on success.
        """
        pass
    # -- End Method authenticate_request

    @abstractmethod
    def register_bot_webhook(self) -> None:
        """
        Register inbound webhooks with the chat platform after HTTP routes are live
        (e.g. ``POST .../bot/<bot_key>``). Use ``self.endpoint`` and ``self.bot_key`` as needed.
        """
        pass
    # -- End Method register_bot_webhook

    def hears(self, pattern: str, priority: int=50):
        """Decorator to register a regex pattern to a handler."""
        def decorator(handler: BotHearsHandler):
            self._hears_routes.append((priority,re.compile(pattern, re.IGNORECASE), handler))
            self._hears_routes.sort(key=lambda x: x[0])
            return handler
        return decorator

    def on_action(self, handler):
        """Decorator to register a callback for card actions."""
        self._action_callbacks.append(handler)
        return handler
# -- End Class BaseChatBot

class BaseChatBotConfig(BaseModel):
    name: str
    # Public HTTPS URL for this bot's events (factory default: ``{base_url}/bot/{bot_key}``).
    endpoint: str
    high_pri_on: Optional[bool] = True
    send_alerts: Optional[bool] = True
    responders: List[str]
    room_title_template: Optional[str] = '{{requester_name}} - {{team_description}} {{date}}'
    # Alert plugin module name under ``alerts.plugins``; use ``null`` when send_alerts is False.
    alert_type: str = "null"
    team_description: str
    emergency_warning_message: Optional[str]

    @model_validator(mode='after')
    def consistent_alert_settings(self) -> "BaseChatBotConfig":
        if self.send_alerts and self.alert_type == "null":
            raise ValueError(
                f"{self.name}: send_alerts=True requires alert_type other than 'null'."
            )

        if not self.send_alerts and self.alert_type != "null":
            raise ValueError(
                f"{self.name}: send_alerts=False requires alert_type='null'."
            )

        if self.high_pri_on:
            if not self.send_alerts:
                raise ValueError(
                    f"{self.name}: high_pri_on=True requires send_alerts to also be True."
                )

        return self
    # -- End consistent_alert_settings