# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# lookup/base.py
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select

from gemstone_utils.db import get_session

from lookup.models import (
    SchemaPerson,
    SchemaPlatformId,
    SchemaTeam,
    SchemaTeamMember,
    SchemaTeamPlatformId,
)
from thaum.types import RespondersList, ThaumPerson, ThaumTeam

logger = logging.getLogger("thaum.lookup")

ONE_WEEK = 604800


class BaseLookupPluginConfig(BaseModel):
    """
    Shared lookup cache configuration for all lookup plugins.

    The process-global DB is opened via :func:`gemstone_utils.db.init_db` (see
    :func:`thaum.db_bootstrap.init_app_db` / server bootstrap). Configure the URL under
    ``[server.database].db_url``, not here.

    Expected TOML:
      [lookup]
      default_team_ttl_seconds = 14400

    Plugin-specific overrides go under:
      [lookup.<plugin_name>]
    """

    default_team_ttl_seconds: int = 14400

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

# -- End Class BaseLookupPluginConfig


class BaseLookupPlugin(ABC):
    """
    Base class for lookup/caching plugins.

    Persistence uses ORM models on :class:`gemstone_utils.db.GemstoneDB` (tables prefixed
    with ``schema_`` for portability). Call :func:`thaum.db_bootstrap.init_app_db`
    before constructing plugins.

    Identity cache rules:
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

    plugin_name: str = "lookup"

    def __init__(
        self,
        *,
        default_team_ttl_seconds: int = 14400,
    ):
        self.logger = logging.getLogger(f"lookup.{self.plugin_name}")
        self._default_team_ttl_seconds = default_team_ttl_seconds

    # --- People ---------------------------------------------------------------

    def get_person_by_id(
        self, bot_plugin_name: str, person_id: str
    ) -> Optional[ThaumPerson]:
        """
        Return a cached ThaumPerson for a bot/agent plugin id.

        Cache lookup key is the bot/plugin name (e.g. `webex`, `jira`, `ldap`).
        """
        with get_session() as session:
            row = session.scalar(
                select(SchemaPlatformId.email).where(
                    SchemaPlatformId.platform_key == bot_plugin_name,
                    SchemaPlatformId.platform_id == person_id,
                )
            )
            if not row:
                return None
            return self._get_person_by_email(session, row)

    def _get_person_by_email(
        self, session: Any, email: str
    ) -> Optional[ThaumPerson]:
        row = session.get(SchemaPerson, email)
        if row is None:
            return None

        pid_rows = session.scalars(
            select(SchemaPlatformId).where(SchemaPlatformId.email == email)
        ).all()

        platform_ids: Dict[str, str] = {p.platform_key: p.platform_id for p in pid_rows}

        return ThaumPerson(
            email=row.email,
            display_name=row.display_name or "",
            platform_ids=platform_ids,
            source_plugin=row.source_plugin or self.plugin_name,
        )

    def get_person_by_email(self, email: str) -> Optional[ThaumPerson]:
        """Return a cached person by canonical email, if present."""
        key = (email or "").strip()
        if not key:
            return None
        with get_session() as session:
            return self._get_person_by_email(session, key)

    def merge_person(self, fragment: ThaumPerson) -> ThaumPerson:
        """
        Merge a partial ThaumPerson fragment into the canonical cache row
        by email, then return the fully merged ThaumPerson.
        """
        now = time.time()

        with get_session() as session:
            with session.begin():
                existing = session.get(SchemaPerson, fragment.email)

                if existing:
                    should_update_name = (
                        not existing.display_name
                        or existing.display_name.strip() == ""
                        or (now - existing.name_last_updated) > ONE_WEEK
                    )

                    if should_update_name and fragment.display_name:
                        existing.display_name = fragment.display_name
                        existing.source_plugin = fragment.source_plugin
                        existing.name_last_updated = now
                else:
                    session.add(
                        SchemaPerson(
                            email=fragment.email,
                            display_name=fragment.display_name,
                            source_plugin=fragment.source_plugin,
                            name_last_updated=now,
                        )
                    )

                for platform_key, pid in fragment.platform_ids.items():
                    dup = session.scalar(
                        select(SchemaPlatformId).where(
                            SchemaPlatformId.platform_key == platform_key,
                            SchemaPlatformId.platform_id == pid,
                        )
                    )
                    if dup is None:
                        session.add(
                            SchemaPlatformId(
                                platform_key=platform_key,
                                platform_id=pid,
                                email=fragment.email,
                            )
                        )

                merged = self._get_person_by_email(session, fragment.email)
                assert merged is not None
                return merged

    def resolve_responder_refs(
        self,
        bot: Any,
        refs: List[str],
        *,
        source_plugin: str = "config",
        team_name_normalizer: Optional[Callable[[str], str]] = None,
    ) -> RespondersList:
        """
        Resolve responder references into a typed RespondersList via cached people/teams.

        Supported refs:
          - person:<email>
          - team:<team_name>
          - plain email (contains '@')
          - bare team name
        """
        out = RespondersList()
        normalize = team_name_normalizer or (lambda s: s.strip())

        for raw in refs:
            ref = (raw or "").strip()
            if not ref:
                continue

            if ref.lower().startswith("person:"):
                email = ref[7:].strip()
                if email:
                    out += ThaumPerson(email=email)
                continue

            if ref.lower().startswith("team:"):
                team_name = normalize(ref[5:])
                if not team_name:
                    continue
                team = self.get_team_by_name(bot, team_name)
                if team is not None:
                    out += team
                else:
                    self.logger.warning("Responder team '%s' was not found in lookup cache.", team_name)
                continue

            if "@" in ref:
                out += ThaumPerson(email=ref)
                continue

            team_name = normalize(ref)
            if not team_name:
                continue
            team = self.get_team_by_name(bot, team_name)
            if team is not None:
                out += team
            else:
                self.logger.warning("Responder reference '%s' did not resolve as person or team.", ref)

        return out

    # --- Teams ---------------------------------------------------------------

    def get_team_by_name(self, bot: Any, team_name: str) -> Optional[ThaumTeam]:
        with get_session() as session:
            row = session.get(SchemaTeam, team_name)
            if row is None:
                return None

            email_rows = session.scalars(
                select(SchemaTeamMember.email).where(
                    SchemaTeamMember.team_name == team_name
                )
            ).all()

            members: List[ThaumPerson] = []
            for email in email_rows:
                p = self._get_person_by_email(session, email)
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
        with get_session() as session:
            name = session.scalar(
                select(SchemaTeamPlatformId.team_name).where(
                    SchemaTeamPlatformId.platform_key == bot_plugin_name,
                    SchemaTeamPlatformId.platform_id == team_id,
                )
            )
            if not name:
                return None

        return self.get_team_by_name(bot, name)

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
        with get_session() as session:
            with session.begin():
                last_cached = getattr(team, "last_cached", None) or time.time()
                ttl = getattr(team, "ttl", None) or self._default_team_ttl_seconds

                session.merge(
                    SchemaTeam(
                        team_name=team.team_name,
                        last_cached=last_cached,
                        ttl=ttl,
                    )
                )

                session.execute(
                    delete(SchemaTeamMember).where(
                        SchemaTeamMember.team_name == team.team_name
                    )
                )

                members = list(getattr(team, "_members", []))
                for m in members:
                    session.add(
                        SchemaTeamMember(team_name=team.team_name, email=m.email)
                    )

                if bot_plugin_name and team_id:
                    dup = session.scalar(
                        select(SchemaTeamPlatformId).where(
                            SchemaTeamPlatformId.platform_key == bot_plugin_name,
                            SchemaTeamPlatformId.platform_id == team_id,
                        )
                    )
                    if dup is None:
                        session.add(
                            SchemaTeamPlatformId(
                                platform_key=bot_plugin_name,
                                platform_id=team_id,
                                team_name=team.team_name,
                            )
                        )

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
        team._members = members
        return self.merge_team(team, bot_plugin_name=None, team_id=None)._members

    @abstractmethod
    def fetch_team_members(self, team: ThaumTeam) -> List[ThaumPerson]:
        """Fetch team members from the backing system (LDAP/Jira/...)."""
        ...

# -- End Class BaseLookupPlugin
