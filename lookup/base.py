# lookup/base.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import logging
import os
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

from filelock import FileLock
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    delete,
    create_engine,
    select,
    text,
)

from thaum.types import ThaumPerson, ThaumTeam

logger = logging.getLogger("thaum.lookup")

ONE_WEEK = 604800
DEFAULT_CACHE_LOCK_PATH = os.path.join(tempfile.gettempdir(), "thaum_cache.lock")

_metadata = MetaData()

# --- PEOPLE TABLE -------------------------------------------------------------
_people_table = Table(
    "people",
    _metadata,
    Column("email", String, primary_key=True),
    Column("display_name", String, nullable=True),
    Column("source_plugin", String, nullable=True),
    Column("name_last_updated", Float, nullable=False),  # epoch timestamp
)

# --- PLATFORM IDS TABLE ------------------------------------------------------
_platform_ids_table = Table(
    "platform_ids",
    _metadata,
    Column("platform_key", String, nullable=False),  # plugin name: webex, jira, ldap, etc.
    Column("platform_id", String, nullable=False),  # plugin-specific user id
    Column("email", String, ForeignKey("people.email"), nullable=False),
    PrimaryKeyConstraint("platform_key", "platform_id"),
)

# --- TEAMS TABLE --------------------------------------------------------------
_teams_table = Table(
    "teams",
    _metadata,
    Column("team_name", String, primary_key=True),
    Column("last_cached", Float, nullable=False),
    Column("ttl", Integer, nullable=False),
)

# --- TEAM MEMBERS TABLE ------------------------------------------------------
_team_members_table = Table(
    "team_members",
    _metadata,
    Column("team_name", String, ForeignKey("teams.team_name"), nullable=False),
    Column("email", String, ForeignKey("people.email"), nullable=False),
    PrimaryKeyConstraint("team_name", "email"),
)

# --- TEAM PLATFORM IDS TABLE ------------------------------------------------
_team_platform_ids_table = Table(
    "team_platform_ids",
    _metadata,
    Column("platform_key", String, nullable=False),
    Column("platform_id", String, nullable=False),
    Column("team_name", String, ForeignKey("teams.team_name"), nullable=False),
    PrimaryKeyConstraint("platform_key", "platform_id"),
)

class BaseLookupPluginConfig(BaseModel):
    """
    Shared SQLAlchemy cache configuration for all lookup plugins.

    Expected TOML:
      [lookup]
      db_url = "..."
      cache_lock_path = "/path/to/lock"
      default_team_ttl_seconds = 14400

    Plugin-specific overrides go under:
      [lookup.<plugin_name>]
    """

    db_url: str = "sqlite:///thaum_lookup_cache.db"
    cache_lock_path: Optional[str] = None
    default_team_ttl_seconds: int = 14400

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

# -- End Class BaseLookupPluginConfig

class BaseLookupPlugin(ABC):
    """
    Base class for lookup/caching plugins.

    Identity cache rules (SQLAlchemy):
      - People are cached by (platform_key, platform_id) -> email -> ThaumPerson.
      - Teams are cached by team name, and optionally mapped by (platform_key, platform_id) -> team_name.

    Intended call flow:
      1. Caller asks for cached person by bot plugin key:
         `get_person_by_id(bot_plugin_name, person_id)`
      2. If miss, caller does the platform API lookup and builds a *partial*
         `ThaumPerson` keyed by email.
      3. Caller passes that partial object to `merge_person(fragment)` so the cache
         merges by email (and persists any new platform ids).
    """

    #: Optional: the cache instance is shared by a single server.
    plugin_name: str = "lookup"

    def __init__(
        self,
        db_url: str = "sqlite:///thaum_lookup_cache.db",
        *,
        cache_lock_path: Optional[str] = None,
        default_team_ttl_seconds: int = 14400,
    ):
        self.logger = logging.getLogger(f"lookup.{self.plugin_name}")
        self._engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self._cache_lock_path = cache_lock_path or DEFAULT_CACHE_LOCK_PATH
        self._default_team_ttl_seconds = default_team_ttl_seconds
        _metadata.create_all(self._engine)

        # Improve concurrent read/write behavior under gunicorn by enabling WAL
        # when using SQLite.
        if db_url.strip().lower().startswith("sqlite"):
            try:
                with self._engine.begin() as conn:
                    conn.execute(text("PRAGMA journal_mode=WAL"))
            except Exception as e:
                self.logger.warning("Failed to enable SQLite WAL: %s", e)

    # --- People ---------------------------------------------------------------

    def get_person_by_id(
        self, bot_plugin_name: str, person_id: str
    ) -> Optional[ThaumPerson]:
        """
        Return a cached ThaumPerson for a bot/agent plugin id.

        Cache lookup key is the bot/plugin name (e.g. `webex`, `jira`, `ldap`).
        """
        with self._engine.begin() as conn:
            row = conn.execute(
                select(_platform_ids_table.c.email).where(
                    _platform_ids_table.c.platform_key == bot_plugin_name
                ).where(_platform_ids_table.c.platform_id == person_id)
            ).fetchone()

            if not row:
                return None

            return self._get_person_by_email(conn, row.email)

    def _get_person_by_email(
        self, conn: Any, email: str
    ) -> Optional[ThaumPerson]:
        row = conn.execute(
            select(_people_table).where(_people_table.c.email == email)
        ).fetchone()
        if not row:
            return None

        pid_rows = conn.execute(
            select(_platform_ids_table).where(_platform_ids_table.c.email == email)
        ).fetchall()

        platform_ids: Dict[str, str] = {r.platform_key: r.platform_id for r in pid_rows}

        return ThaumPerson(
            email=row.email,
            display_name=row.display_name or "",
            platform_ids=platform_ids,
            source_plugin=row.source_plugin or self.plugin_name,
        )

    def merge_person(self, fragment: ThaumPerson) -> ThaumPerson:
        """
        Merge a partial ThaumPerson fragment into the canonical cache row
        by email, then return the fully merged ThaumPerson.
        """
        now = time.time()

        with FileLock(self._cache_lock_path):
            with self._engine.begin() as conn:
                existing = conn.execute(
                    select(_people_table).where(_people_table.c.email == fragment.email)
                ).fetchone()

                if existing:
                    should_update_name = (
                        not existing.display_name
                        or existing.display_name.strip() == ""
                        or (now - existing.name_last_updated) > ONE_WEEK
                    )

                    update_values: Dict[str, Any] = {}
                    if should_update_name and fragment.display_name:
                        update_values["display_name"] = fragment.display_name
                        update_values["source_plugin"] = fragment.source_plugin
                        update_values["name_last_updated"] = now

                    if update_values:
                        conn.execute(
                            _people_table.update()
                            .where(_people_table.c.email == fragment.email)
                            .values(**update_values)
                        )
                else:
                    conn.execute(
                        _people_table.insert().values(
                            email=fragment.email,
                            display_name=fragment.display_name,
                            source_plugin=fragment.source_plugin,
                            name_last_updated=now,
                        )
                    )

                # Insert platform ids (duplicates are OK to ignore).
                for platform_key, pid in fragment.platform_ids.items():
                    try:
                        conn.execute(
                            _platform_ids_table.insert().values(
                                platform_key=platform_key,
                                platform_id=pid,
                                email=fragment.email,
                            )
                        )
                    except Exception:
                        pass

                return self._get_person_by_email(conn, fragment.email)

    # --- Teams ---------------------------------------------------------------

    def get_team_by_name(self, bot: Any, team_name: str) -> Optional[ThaumTeam]:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(_teams_table).where(_teams_table.c.team_name == team_name)
            ).fetchone()

            if not row:
                return None

            email_rows = conn.execute(
                select(_team_members_table.c.email).where(
                    _team_members_table.c.team_name == team_name
                )
            ).fetchall()

            # Convert to ThaumPerson objects using the same connection.
            members: List[ThaumPerson] = []
            for r in email_rows:
                p = self._get_person_by_email(conn, r.email)
                if p is not None:
                    members.append(p)

        return ThaumTeam(
            bot=bot,
            team_name=team_name,
            last_cached=row.last_cached,
            ttl=row.ttl,
            _members=members,
        )

    def get_team_by_id(
        self, bot: Any, bot_plugin_name: str, team_id: str
    ) -> Optional[ThaumTeam]:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(_team_platform_ids_table.c.team_name).where(
                    _team_platform_ids_table.c.platform_key == bot_plugin_name
                ).where(_team_platform_ids_table.c.platform_id == team_id)
            ).fetchone()

            if not row:
                return None

            return self.get_team_by_name(bot, row.team_name)

    def cache_team(
        self,
        team: ThaumTeam,
        *,
        bot_plugin_name: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> ThaumTeam:
        """
        Persist the team's member snapshot into the identity cache.

        If `bot_plugin_name` and `team_id` are provided, also store a lookup
        mapping so callers can do `get_team_by_id(...)` by (plugin,id).
        """
        with FileLock(self._cache_lock_path):
            with self._engine.begin() as conn:
                last_cached = getattr(team, "last_cached", None) or time.time()
                ttl = getattr(team, "ttl", None) or self._default_team_ttl_seconds

                conn.execute(
                    _teams_table.insert()
                    .values(
                        team_name=team.team_name,
                        last_cached=last_cached,
                        ttl=ttl,
                    )
                    .prefix_with("OR REPLACE")  # SQLite-compatible
                )

                conn.execute(
                    delete(_team_members_table).where(
                        _team_members_table.c.team_name == team.team_name
                    )
                )

                members = list(getattr(team, "_members", []))
                if members:
                    conn.execute(
                        _team_members_table.insert(),
                        [{"team_name": team.team_name, "email": m.email} for m in members],
                    )

                if bot_plugin_name and team_id:
                    try:
                        conn.execute(
                            _team_platform_ids_table.insert().values(
                                platform_key=bot_plugin_name,
                                platform_id=team_id,
                                team_name=team.team_name,
                            )
                        )
                    except Exception:
                        # Mapping already exists; ignore.
                        pass

        # Keep/return the live object reference. Callers still get cached members from DB via
        # `get_team_by_name(...)` if they need full reconstruction.
        return team

    def merge_team(
        self,
        team: ThaumTeam,
        *,
        bot_plugin_name: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> ThaumTeam:
        """
        Merge team members into the people cache (by email), then persist the team
        membership snapshot.
        """
        members = list(getattr(team, "_members", []))
        merged: List[ThaumPerson] = []
        for m in members:
            try:
                merged.append(self.merge_person(m))
            except Exception as e:
                self.logger.warning("Failed to merge team member %s: %s", getattr(m, "email", m), e)
                merged.append(m)

        team._members = merged
        team.last_cached = time.time()
        if not getattr(team, "ttl", None):
            team.ttl = self._default_team_ttl_seconds

        self.cache_team(team, bot_plugin_name=bot_plugin_name, team_id=team_id)
        return team

    def lookup_team_members(self, team: ThaumTeam) -> List[ThaumPerson]:
        """
        Fetch current team members from the backing source and persist them.

        Return value is a merged list of ThaumPerson objects.
        """
        members = self.fetch_team_members(team)
        # Persist requires `team._members` so `merge_team(...)` can merge by email.
        team._members = members
        return self.merge_team(team, bot_plugin_name=None, team_id=None)._members

    @abstractmethod
    def fetch_team_members(self, team: ThaumTeam) -> List[ThaumPerson]:
        """Fetch team members from the backing system (LDAP/Jira/...)."""
        ...

# -- End Class BaseLookupPlugin

