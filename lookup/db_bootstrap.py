# lookup/db_bootstrap.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import logging
from typing import Any, Dict

from gemstone_utils.db import init_db
from thaum.types import ServerConfig

from lookup.base import DEFAULT_LOOKUP_DB_URL

logger = logging.getLogger("thaum.lookup.db_bootstrap")


def merged_lookup_plugin_config(lookup_type: str, lookup_raw: Dict[str, Any]) -> Dict[str, Any]:
    """Match ``lookup/factory.create_lookup`` merge rules for ``[lookup]`` + ``[lookup.<type>]``."""
    plugin_cfg = lookup_raw.get(lookup_type, {}) if isinstance(lookup_raw, dict) else {}
    merged: Dict[str, Any] = dict(lookup_raw or {})
    if isinstance(plugin_cfg, dict):
        merged.update(plugin_cfg)
    return merged


def resolve_app_db_url(server_cfg: ServerConfig) -> str:
    """Resolve SQLAlchemy URL from ``[server.database].db_spec`` (default: in-memory SQLite)."""
    raw = server_cfg.database.db_spec
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DEFAULT_LOOKUP_DB_URL
    return str(raw).strip()


def engine_kwargs_for_sqlite_url(db_url: str) -> Dict[str, Any]:
    """SQLite in-memory needs a single shared connection pool across sessions."""
    u = db_url.strip().lower()
    if not u.startswith("sqlite"):
        return {}
    if ":memory:" not in u:
        return {}
    from sqlalchemy.pool import StaticPool

    return {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }


def init_lookup_db(db_url: str, *, echo: bool = False, **engine_kw: Any) -> None:
    """
    Register lookup ORM models and call :func:`gemstone_utils.db.init_db`.

    Import this module (or ``lookup.models``) before :func:`init_db` so tables exist on
    :class:`gemstone_utils.db.GemstoneDB` metadata. Jira alert correlation rows live in
    ``alerts.plugins.jira.models`` and are registered here so ``init_db`` creates the table.
    """
    import lookup.models  # noqa: F401 — register ORM tables
    import alerts.plugins.jira.models  # noqa: F401 — register Jira ORM tables
    import thaum.admin_models  # noqa: F401 — admin log-level nonce + state
    import thaum.webhook_bearer_warn  # noqa: F401 — webhook bearer warn throttle
    import gemstone_utils.election  # noqa: F401 — election ORM tables
    import gemstone_utils.sqlalchemy.key_storage  # noqa: F401 — GemstoneKeyKdf / GemstoneKeyRecord
    import thaum.crypto_metadata  # noqa: F401 — thaum_crypto_metadata
    import thaum.bot_webhook_state  # noqa: F401 — bot_webhook_hmac
    import gemstone_utils.election  # noqa: F401 — election ORM tables
    import gemstone_utils.sqlalchemy.key_storage  # noqa: F401 — GemstoneKeyKdf / GemstoneKeyRecord
    import thaum.crypto_metadata  # noqa: F401 — thaum_crypto_metadata
    import thaum.bot_webhook_state  # noqa: F401 — bot_webhook_hmac

    merged_kw: Dict[str, Any] = {**engine_kwargs_for_sqlite_url(db_url), **engine_kw}
    init_db(db_url, echo=echo, **merged_kw)
    logger.debug("Lookup ORM tables ensured via gemstone_utils.db.init_db")
