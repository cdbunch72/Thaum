#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
set -e

ext_raw="${THAUM_EXTERNAL_DB:-}"
ext="$(printf %s "$ext_raw" | tr '[:upper:]' '[:lower:]')"
case "$ext" in
  1|true|yes|on) EXTERNAL=1 ;;
  *) EXTERNAL=0 ;;
esac

if [ "$EXTERNAL" = 1 ]; then
  exec gosu thaum /venv/bin/gunicorn \
    --bind "${GUNICORN_BIND:-0.0.0.0:5165}" \
    --workers "${GUNICORN_WORKERS:-1}" \
    app:app
fi

export PGDATA="${PGDATA:-/var/lib/thaum/postgresql/data}"
mkdir -p /var/log/thaum/postgresql /run/thaum/postgres /var/log/supervisor
chown postgres:postgres /run/thaum/postgres /var/log/thaum/postgresql
mkdir -p "$PGDATA"
chown postgres:postgres "$PGDATA"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  gosu postgres initdb -D "$PGDATA"
  cat > "$PGDATA/postgresql.auto.conf" <<'EOF'
listen_addresses = ''
unix_socket_directories = '/run/thaum/postgres'
EOF
  touch "$PGDATA/.thaum_configured"
elif [ ! -f "$PGDATA/.thaum_configured" ]; then
  cat > "$PGDATA/postgresql.auto.conf" <<'EOF'
listen_addresses = ''
unix_socket_directories = '/run/thaum/postgres'
EOF
  touch "$PGDATA/.thaum_configured"
fi

gosu postgres pg_ctl -D "$PGDATA" -l /var/log/thaum/postgresql/postgres-init.log start -w
gosu postgres /venv/bin/python /app/docker/pg_bootstrap.py
gosu postgres pg_ctl -D "$PGDATA" stop -m fast

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
