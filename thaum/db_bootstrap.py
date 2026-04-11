# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/db_bootstrap.py
"""Application-wide SQLAlchemy database initialization (ORM registration + engine)."""
from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy import create_engine, text

from gemstone_utils.db import init_db
from thaum.types import ServerConfig

logger = logging.getLogger("thaum.db_bootstrap")

DEFAULT_APP_DB_URL = "sqlite:///:memory:"


def resolve_app_db_url(server_cfg: ServerConfig) -> str:
    """Resolve SQLAlchemy URL from ``[server.database].db_url`` (default: in-memory SQLite)."""
    raw = server_cfg.database.db_url
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DEFAULT_APP_DB_URL
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


def verify_app_db_connection(db_url: str, **engine_kw: Any) -> None:
    """
    Open a connection and run ``SELECT 1`` to verify URL, driver, auth, and network.
    Does not create application tables (see :func:`init_app_db`).
    """
    merged_kw: Dict[str, Any] = {**engine_kwargs_for_sqlite_url(db_url), **engine_kw}
    engine = create_engine(db_url, **merged_kw)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def init_app_db(db_url: str, *, echo: bool = False, **engine_kw: Any) -> None:
    """
    Register all Thaum ORM models on :class:`gemstone_utils.db.GemstoneDB` metadata and call
    :func:`gemstone_utils.db.init_db`.

    Import side effects cover lookup cache tables, Jira alert correlation, admin log state,
    webhook throttles, election, encrypted key storage, and bot webhook HMAC rows.
    """
    import lookup.models  # noqa: F401 — register ORM tables
    import alerts.plugins.jira.models  # noqa: F401 — register Jira ORM tables
    import thaum.admin_models  # noqa: F401 — admin log-level nonce + state
    import thaum.webhook_bearer_warn  # noqa: F401 — webhook bearer warn throttle
    import gemstone_utils.election  # noqa: F401 — election ORM tables
    import gemstone_utils.sqlalchemy.key_storage  # noqa: F401 — GemstoneKeyKdf / GemstoneKeyRecord
    import thaum.bot_webhook_state  # noqa: F401 — bot_webhook_hmac

    merged_kw: Dict[str, Any] = {**engine_kwargs_for_sqlite_url(db_url), **engine_kw}
    init_db(db_url, echo=echo, **merged_kw)
    logger.debug("Application ORM tables ensured via gemstone_utils.db.init_db")
