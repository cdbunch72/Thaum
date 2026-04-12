#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
"""Create bundled PostgreSQL role and database (peer auth; run as postgres OS user)."""
from __future__ import annotations

import os

import psycopg
from psycopg import sql


def main() -> int:
    user = (os.environ.get("THAUM_PG_USER") or "thaum").strip() or "thaum"
    dbname = (os.environ.get("THAUM_PG_DATABASE") or "thaum").strip() or "thaum"
    sock = (os.environ.get("THAUM_PG_SOCKET_DIR") or "/run/thaum/postgres").strip() or "/run/thaum/postgres"

    conn_str = f"host={sock} user=postgres dbname=postgres"
    conn = psycopg.connect(conn_str)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s",
                (user,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE ROLE {} LOGIN CREATEDB").format(sql.Identifier(user))
                )
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (dbname,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(dbname),
                        sql.Identifier(user),
                    )
                )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
