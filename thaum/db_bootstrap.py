# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/db_bootstrap.py
"""Application-wide SQLAlchemy database initialization (ORM registration + engine)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

from gemstone_utils.db import init_db
from thaum.types import ServerConfig

logger = logging.getLogger("thaum.db_bootstrap")

DEFAULT_PG_USER = "thaum"
DEFAULT_PG_DATABASE = "thaum"
DEFAULT_PG_SOCKET_DIR = "/tmp/postgres"


def _external_db_env_true() -> bool:
    """True when ``THAUM_EXTERNAL_DB`` requests an external-only deployment (no bundled default)."""
    v = os.environ.get("THAUM_EXTERNAL_DB", "").strip().lower()
    if not v:
        return False
    return v in ("1", "true", "yes", "on")


def _ensure_psycopg_client_encoding_utf8(db_url: str) -> str:
    """
    Append ``client_encoding=utf8`` to ``postgresql+psycopg://`` URLs when missing.

    If the session uses ``SQL_ASCII`` (no real encoding), psycopg3 returns ``bytes``
    for text; SQLAlchemy then fails in ``_get_server_version_info`` (regex expects
    ``str``). See https://github.com/psycopg/psycopg/issues/813
    """
    u = db_url.strip()
    if not u.lower().startswith("postgresql+psycopg://"):
        return u
    if "client_encoding=" in u.lower():
        return u
    return f"{u}{'&' if '?' in u else '?'}client_encoding=utf8"


def default_bundled_db_url() -> str:
    """
    SQLAlchemy URL for the bundled PostgreSQL instance (Unix socket only).

    Uses **peer** authentication: the OS user running Thaum (``thaum`` in the
    container) must match the role name. No password is embedded in the URL.

    Optional env: ``THAUM_PG_USER``, ``THAUM_PG_DATABASE``, ``THAUM_PG_SOCKET_DIR``
    (see module defaults).
    """
    user = (os.environ.get("THAUM_PG_USER") or DEFAULT_PG_USER).strip() or DEFAULT_PG_USER
    dbname = (os.environ.get("THAUM_PG_DATABASE") or DEFAULT_PG_DATABASE).strip() or DEFAULT_PG_DATABASE
    sock_dir = (os.environ.get("THAUM_PG_SOCKET_DIR") or DEFAULT_PG_SOCKET_DIR).strip() or DEFAULT_PG_SOCKET_DIR
    return _ensure_psycopg_client_encoding_utf8(
        f"postgresql+psycopg://{quote_plus(user)}@/{quote_plus(dbname)}?host={quote_plus(sock_dir)}"
    )


def resolve_app_db_url(server_cfg: ServerConfig) -> str:
    """
    Resolve SQLAlchemy URL from ``[server.database].db_url``.

    If ``db_url`` is unset or empty: when ``THAUM_EXTERNAL_DB`` is true, raises
    ``ValueError`` (must set an explicit ``db_url``); otherwise returns the
    bundled PostgreSQL URL from :func:`default_bundled_db_url`.
    """
    raw = server_cfg.database.db_url
    if raw is not None and isinstance(raw, str) and raw.strip():
        return _ensure_psycopg_client_encoding_utf8(str(raw).strip())

    if _external_db_env_true():
        raise ValueError(
            "[server.database].db_url is required when THAUM_EXTERNAL_DB is set (true/yes/1)."
        )

    return default_bundled_db_url()


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
