# bots/base.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from abc import ABC, abstractmethod
from __future__ import annotations
from typing import List, Optional, Tuple, Callable, Dict, Any, Protocol
from thaum.types import ThaumPerson
from dataclasses import dataclass, field
from pydantic import BaseModel, model_validator
import re

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
        self.send_alerts = config.send_alerts
        self.high_pri_on = config.high_pri_on
        self.alert_plugin_type = config.alert_plugin_type
        self.responders = config.responders
        self.team_description = config.team_description
        self.room_title_template = config.room_title_template
        self.emergency_warning_message = config.emergency_warning_message
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
    high_pri_on: Optional[bool] = True
    send_alerts: Optional[bool] = True
    responders: List[str]
    room_title_template: Optional[str] = '{{requester_name}} - {{team_description}} {{date}}'
    alert_plugin_type: Optional[str] = 'NullPlugin'
    team_description: str
    emergency_warning_message: Optional[str]

    @model_validator(mode='after')
    def consistent_alert_settings(self) -> 'BaseChatBotConfig':
        # --- Rule 1: send_alerts requires a real plugin ---
        if self.send_alerts and self.alert_plugin_type == "NullPlugin":
            raise ValueError(
                f"{self.name}: send_alerts=True requires alert_plugin_type != 'NullPlugin'."
            )

        # --- Rule 2: no alerts means NullPlugin must be selected ---
        if not self.send_alerts and self.alert_plugin_type != "NullPlugin":
            raise ValueError(
                f"{self.name}: send_alerts=False requires alert_plugin_type='NullPlugin'."
            )

        # --- Rule 3: high priority requires the other toggles ---
        if self.high_pri_on:
            if not self.send_alerts:
                raise ValueError(
                    f" {self.name}: high_pri_on=True requires send_alerts to also be True."
                )

        return self
    # -- End consistent_alert_settings