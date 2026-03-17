# thaum/identity.py
# Copyright 2026 <<Name>>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import time
import logging
from typing import Optional, List
from sqlalchemy import (
    create_engine,
    Table,
    Column,
    String,
    Integer,
    Float,
    ForeignKey,
    MetaData,
    PrimaryKeyConstraint,
    select,
    delete
)
from thaum.types import ThaumPerson, ThaumTeam

from filelock import FileLock


CACHE_LOCK = "/run/thaum/cache.lock"
ONE_WEEK = 604800

logger = logging.getLogger("thaum.identity")
metadata = MetaData()

# --- Schema Definition ---
# -----------------------------
# PEOPLE TABLE
# -----------------------------
people_table = Table(
    "people",
    metadata,
    Column("email", String, primary_key=True),
    Column("display_name", String, nullable=True),
    Column("source_plugin", String, nullable=True),
    Column("name_last_updated", Float, nullable=False),  # epoch timestamp
)

# -----------------------------
# PLATFORM IDS TABLE
# -----------------------------
platform_ids_table = Table(
    "platform_ids",
    metadata,
    Column("platform_key", String, nullable=False),   # plugin name
    Column("platform_id", String, nullable=False),    # plugin-specific user ID
    Column("email", String, ForeignKey("people.email"), nullable=False),

    PrimaryKeyConstraint("platform_key", "platform_id")
)

# -----------------------------
# TEAMS TABLE
# -----------------------------
teams_table = Table(
    "teams",
    metadata,
    Column("team_name", String, primary_key=True),
    Column("last_cached", Float, nullable=False),
    Column("ttl", Integer, nullable=False),
)

# -----------------------------
# TEAM MEMBERS TABLE
# -----------------------------
team_members_table = Table(
    "team_members",
    metadata,
    Column("team_name", String, ForeignKey("teams.team_name"), nullable=False),
    Column("email", String, ForeignKey("people.email"), nullable=False),

    PrimaryKeyConstraint("team_name", "email")
)
# --- Internal Module State ---
_engine = None

def init_identity_db(db_url: str):
    global _engine
    _engine = create_engine(db_url, connect_args={"check_same_thread": False})
    metadata.create_all(_engine)
# -- End Function init_identity_db

# --- Functional API ---


def get_person_by_email(email: str) -> ThaumPerson:
    with _engine.begin() as conn:
        row = conn.execute(
            select(people_table).where(people_table.c.email == email)
        ).fetchone()

        if not row:
            return None  # or raise

        pid_rows = conn.execute(
            select(platform_ids_table).where(platform_ids_table.c.email == email)
        ).fetchall()

    platform_ids = {r.platform_key: r.platform_id for r in pid_rows}

    return ThaumPerson(
        email=row.email,
        display_name=row.display_name,
        source_plugin=row.source_plugin,
        platform_ids=platform_ids,
    )
# -- End get_person_by_email

def resolve_person(fragment: ThaumPerson) -> ThaumPerson:
    """
    Merge a partial ThaumPerson fragment into the canonical identity record,
    then return the fully merged ThaumPerson.
    """
    now = time.time()

    with FileLock(CACHE_LOCK):
        with _engine.begin() as conn:
            existing = conn.execute(
                select(people_table).where(people_table.c.email == fragment.email)
            ).fetchone()

            if existing:
                should_update_name = (
                    not existing.display_name
                    or existing.display_name.strip() == ""
                    or (now - existing.name_last_updated) > ONE_WEEK
                )

                update_values = {}
                if should_update_name and fragment.display_name:
                    update_values["display_name"] = fragment.display_name
                    update_values["source_plugin"] = fragment.source_plugin
                    update_values["name_last_updated"] = now

                if update_values:
                    conn.execute(
                        people_table.update()
                        .where(people_table.c.email == fragment.email)
                        .values(**update_values)
                    )
            else:
                conn.execute(
                    people_table.insert().values(
                        email=fragment.email,
                        display_name=fragment.display_name,
                        source_plugin=fragment.source_plugin,
                        name_last_updated=now,
                    )
                )
            # -- End if existing
            for plugin_name, pid in fragment.platform_ids.items():
                try:
                    conn.execute(
                        platform_ids_table.insert().values(
                            platform_key=plugin_name,
                            platform_id=pid,
                            email=fragment.email,
                        )
                    )
                except Exception:
                    pass
        # -- End with con
    # -- End with FileLock

    return get_person_by_email(fragment.email)

# -- End Function resolve_person


def get_person_by_id(platform: str, p_id: str) -> Optional[ThaumPerson]:
    with _engine.begin() as conn:
        row = conn.execute(
            select(platform_ids_table.c.email)
            .where(platform_ids_table.c.platform_key == platform)
            .where(platform_ids_table.c.platform_id == p_id)
        ).fetchone()

    return get_person_by_email(row.email) if row else None
# -- End get_person_by_id

def cache_team(t: ThaumTeam) -> Optional[ThaumTeam]:
    with _engine.begin() as conn:

        # 1. Insert or replace team row
        conn.execute(
            teams_table.insert()
            .values(
                team_name=t.team_name,
                last_cached=t.last_cached,
                ttl=t.ttl
            )
            .prefix_with("OR REPLACE")  # SQLite-compatible
        )

        # 2. Delete existing members
        conn.execute(
            delete(team_members_table)
            .where(team_members_table.c.team_name == t.team_name)
        )

        # 3. Insert new members
        if t.members:
            conn.execute(
                team_members_table.insert(),
                [
                    {"team_name": t.team_name, "email": m.email}
                    for m in t.members
                ]
            )

    # 4. Return the merged team
    return get_team(t.team_name)
# -- End cache_team

def get_team(name: str) -> Optional[ThaumTeam]:
    with _engine.begin() as conn:

        # 1. Fetch team row
        row = conn.execute(
            select(teams_table)
            .where(teams_table.c.team_name == name)
        ).fetchone()

        if not row:
            return None

        # 2. Fetch member emails
        email_rows = conn.execute(
            select(team_members_table.c.email)
            .where(team_members_table.c.team_name == name)
        ).fetchall()

    # 3. Convert to ThaumPerson objects
    members = [get_person_by_email(e.email) for e in email_rows]

    # 4. Build the team object
    return ThaumTeam(
        team_name=name,
        members=members,
        last_cached=row.last_cached,
        ttl=row.ttl
    )
# -- End get_team