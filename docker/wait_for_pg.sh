#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
set -e
sock="${THAUM_PG_SOCKET_DIR:-/var/run/postgresql}"
i=0
while [ "$i" -lt 120 ]; do
  if pg_isready -h "$sock" -U postgres -d postgres >/dev/null 2>&1; then
    exit 0
  fi
  i=$((i + 1))
  sleep 0.25
done
echo "wait_for_pg: PostgreSQL did not become ready at ${sock}" >&2
exit 1
