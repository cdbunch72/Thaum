# thaum/identity.py
# Copyright 2026 <<Name>>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import sqlite3
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional,TYPE_CHECKING

if TYPE_CHECKING:
    from bots.base import BaseBot

# --- Data Structures ---
@dataclass
class ThaumPerson:
    email: str
    display_name: str
    platform_ids: Dict[str, str] = field(default_factory=dict)
    source_plugin: str = "unknown"

    @property
    def for_display(self) -> str:
        if self.display_name:
            return self.display_name
        return self.email


@dataclass
class ThaumTeam:
    bot: 'BaseBot'
    team_name: str
    members: List[ThaumPerson] = field(default_factory=list)
    last_cached: float = field(default_factory=time.time)
    ttl: int = 14400 

    @property
    def is_fresh(self) -> bool:
        return (time.time() - self.last_cached) < self.ttl

# --- Persistence Layer ---
_local = threading.local()

def _get_conn():
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(":memory:", check_same_thread=False)
        _local.conn.execute("PRAGMA foreign_keys = ON")
        _local.conn.executescript("""
            CREATE TABLE people (email TEXT PRIMARY KEY, display_name TEXT, source_plugin TEXT, name_last_updated REAL);
            CREATE TABLE platform_ids (platform TEXT, platform_id TEXT, email TEXT, PRIMARY KEY (platform, platform_id), FOREIGN KEY(email) REFERENCES people(email) ON DELETE CASCADE);
            CREATE TABLE teams (team_name TEXT PRIMARY KEY, last_cached REAL, ttl INTEGER);
            CREATE TABLE team_members (team_name TEXT, email TEXT, PRIMARY KEY (team_name, email), FOREIGN KEY(email) REFERENCES people(email));
        """)
    return _local.conn

# --- Public API ---

def cache_person(p: ThaumPerson) -> Optional[ThaumPerson]:
    now = time.time()
    one_week = 604800
    with _get_conn():
        _get_conn().execute("""
            INSERT INTO people (email, display_name, source_plugin, name_last_updated) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                display_name = CASE WHEN display_name IS NULL OR display_name = '' OR (? - name_last_updated) > ? THEN excluded.display_name ELSE display_name END,
                source_plugin = CASE WHEN display_name IS NULL OR display_name = '' OR (? - name_last_updated) > ? THEN excluded.source_plugin ELSE source_plugin END,
                name_last_updated = CASE WHEN display_name IS NULL OR display_name = '' OR (? - name_last_updated) > ? THEN ? ELSE name_last_updated END
        """, (p.email, p.display_name, p.source_plugin, now, now, one_week, now, one_week, now, one_week, now, p.email))
        
        for platform, pid in p.platform_ids.items():
            _get_conn().execute("INSERT OR IGNORE INTO platform_ids (platform, platform_id, email) VALUES (?, ?, ?)", (platform, pid, p.email))
    return get_person_by_email(p.email)

def get_person_by_email(email: str) -> Optional[ThaumPerson]:
    row = _get_conn().execute("SELECT email, display_name, source_plugin FROM people WHERE email = ?", (email,)).fetchone()
    if not row: return None
    p_ids = {r[0]: r[1] for r in _get_conn().execute("SELECT platform, platform_id FROM platform_ids WHERE email = ?", (email,)).fetchall()}
    return ThaumPerson(email=row[0], display_name=row[1], platform_ids=p_ids, source_plugin=row[2])

def get_person_by_id(platform: str, p_id: str) -> Optional[ThaumPerson]:
    res = _get_conn().execute("SELECT email FROM platform_ids WHERE platform = ? AND platform_id = ?", (platform, p_id)).fetchone()
    return get_person_by_email(res[0]) if res else None

def cache_team(t: ThaumTeam) -> Optional[ThaumTeam]:
    with _get_conn():
        _get_conn().execute("INSERT OR REPLACE INTO teams (team_name, last_cached, ttl) VALUES (?, ?, ?)", (t.team_name, t.last_cached, t.ttl))
        _get_conn().execute("DELETE FROM team_members WHERE team_name = ?", (t.team_name,))
        _get_conn().executemany("INSERT INTO team_members (team_name, email) VALUES (?, ?)", [(t.team_name, m.email) for m in t.members])
    return get_team(t.team_name)

def get_team(name: str) -> Optional[ThaumTeam]:
    row = _get_conn().execute("SELECT last_cached, ttl FROM teams WHERE team_name = ?", (name,)).fetchone()
    if not row: return None
    
    # Fetch members
    emails = _get_conn().execute("SELECT email FROM team_members WHERE team_name = ?", (name,)).fetchall()
    members = [get_person_by_email(e[0]) for e in emails]
    
    return ThaumTeam(team_name=name, members=members, last_cached=row[0], ttl=row[1])