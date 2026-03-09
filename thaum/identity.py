# thaum/identity.py
# Copyright 2026 <<Name>>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from dataclasses import dataclass, field
from __future__ import annotations 
from typing import Dict, List, Optional, TYPE_CHECKING
import time
import logging

if TYPE_CHECKING:
    from bots.base import BaseBot

logger = logging.getLogger("thaum.identity")

@dataclass
class ThaumPerson:
    email: str
    display_name: str
    platform_ids: Dict[str, str] = field(default_factory=dict)
    source_plugin: str = "unknown"

    def for_display(self) -> str:
        if self.display_name:
            return self.display_name
        return self.email
# -- End dataclass ThaumPerson

@dataclass
class ThaumTeam:
    bot: BaseBot
    team_name: str
    members: List[ThaumPerson] = field(default_factory=list)
    last_cached: float = field(default_factory=time.time)

    def is_fresh(self, ttl_seconds: int = 14400) -> bool:
        return (time.time() - self.last_cached) < ttl_seconds
    
    
    # -- End Method refresh
# -- End dataclass ThaumTeam


# --- Global Identity Registry ---
_ALL_PEOPLE: Dict[str, ThaumPerson] = {}
_PLATFORM_ID_INDEX: Dict[str, ThaumPerson] = {}
_TEAMS: Dict[str, ThaumTeam] = {}

# --- Identity Functions ---

def get_person_by_id(bot_name: str, plugin_name: str, p_id: str) -> Optional[ThaumPerson]:
    return _PLATFORM_ID_INDEX.get(f"{bot_name}:{plugin_name}:{p_id}")

def register_person(bot_name: str, plugin_name: str, p_id: str, email: str, name: str) -> ThaumPerson:
    if email in _ALL_PEOPLE:
        person = _ALL_PEOPLE[email]
    else:
        person = ThaumPerson(email=email, display_name=name, source_plugin=plugin_name)
        _ALL_PEOPLE[email] = person
    
    person.platform_ids[f"{bot_name}:{plugin_name}"] = p_id
    _PLATFORM_ID_INDEX[f"{bot_name}:{plugin_name}:{p_id}"] = person
    return person

# --- Team Functions ---

def get_team(team_name: str) -> Optional[ThaumTeam]:
    """Retrieve team from cache."""
    return _TEAMS.get(team_name)

def register_team(team_name: str, members: List[ThaumPerson]) -> ThaumTeam:
    """Store team in cache."""
    team = ThaumTeam(team_name=team_name, members=members, last_cached=time.time())
    _TEAMS[team_name] = team
    return team