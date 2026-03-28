# lookup/models.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from emerald_utils.db import EmeraldDB

# Lookup ORM types subclass EmeraldDB so :func:`emerald_utils.db.init_db` creates their tables.
# Additional plugins that own SQLAlchemy models should use the same EmeraldDB base.

# Table name prefix (SQLite has no real schemas; use a stable prefix instead).
SCHEMA_PREFIX = "schema_"


class SchemaPerson(EmeraldDB):
    __tablename__ = f"{SCHEMA_PREFIX}people"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_plugin: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name_last_updated: Mapped[float] = mapped_column(Float, nullable=False)


class SchemaPlatformId(EmeraldDB):
    __tablename__ = f"{SCHEMA_PREFIX}platform_ids"

    platform_key: Mapped[str] = mapped_column(String, primary_key=True)
    platform_id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(
        String,
        ForeignKey(f"{SCHEMA_PREFIX}people.email"),
        nullable=False,
    )


class SchemaTeam(EmeraldDB):
    __tablename__ = f"{SCHEMA_PREFIX}teams"

    team_name: Mapped[str] = mapped_column(String, primary_key=True)
    last_cached: Mapped[float] = mapped_column(Float, nullable=False)
    ttl: Mapped[int] = mapped_column(Integer, nullable=False)


class SchemaTeamMember(EmeraldDB):
    __tablename__ = f"{SCHEMA_PREFIX}team_members"

    team_name: Mapped[str] = mapped_column(
        String,
        ForeignKey(f"{SCHEMA_PREFIX}teams.team_name"),
        primary_key=True,
    )
    email: Mapped[str] = mapped_column(
        String,
        ForeignKey(f"{SCHEMA_PREFIX}people.email"),
        primary_key=True,
    )


class SchemaTeamPlatformId(EmeraldDB):
    __tablename__ = f"{SCHEMA_PREFIX}team_platform_ids"

    platform_key: Mapped[str] = mapped_column(String, primary_key=True)
    platform_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_name: Mapped[str] = mapped_column(
        String,
        ForeignKey(f"{SCHEMA_PREFIX}teams.team_name"),
        nullable=False,
    )
