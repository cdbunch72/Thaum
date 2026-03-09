# bots/base.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Callable
from thaum.identity import ThaumPerson
import re

class BaseBot(ABC):
    """
    The Base Contract for all Thaum Bot drivers.
    Any platform-specific driver (Webex, Teams, Slack) must implement these methods.
    """
    
    def __init__(self, name: str, endpoint: str):
        self.name = name
        self.endpoint = endpoint
        # Initialize state here
        self._hears_routes: List[Tuple[re.Pattern, Callable]] = []
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
    def delete_room(self, room_id: str) -> None:
        """Permanently removes/implodes the room."""
        pass
    # -- End Method delete_room
    
    @abstractmethod
    def get_person(person_id: str) -> ThaumPerson:
        """Takes a bot_type-specific person_id and returns a ThaumPerson"""
        pass
    # -- End Method get_person

    def hears(self, pattern: str):
        """Decorator to register a regex pattern to a handler."""
        def decorator(handler):
            self._hears_routes.append((re.compile(pattern, re.IGNORECASE), handler))
            return handler
        return decorator

    def on_action(self, handler):
        """Decorator to register a callback for card actions."""
        self._action_callbacks.append(handler)
        return handler
# -- End Class BaseBot