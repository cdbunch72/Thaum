#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
set -e

# So gunicorn (and similar) do not use /root when dropping to user thaum via gosu/supervisor.
export HOME=/home/thaum

# Stage orchestrator-mounted secrets into a non-root-readable location when requested.
if [ -n "${THAUM_CREDS_DIR:-}" ]; then
  umask 077
  thaum_creds_dir="$THAUM_CREDS_DIR/thaum"
  install -d -m 0700 -o thaum -g thaum "$thaum_creds_dir"

  for secrets_src in /run/secrets /var/run/secrets; do
    [ -d "$secrets_src" ] || continue
    for secrets_file in "$secrets_src"/*; do
      [ -e "$secrets_file" ] || continue
      [ -f "$secrets_file" ] || continue
      install -m 0400 -o thaum -g thaum "$secrets_file" "$thaum_creds_dir/$(basename "$secrets_file")"
    done
  done

  export CREDENTIALS_DIRECTORY="$thaum_creds_dir"
fi

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
sleep 600
gosu postgres pg_ctl -D "$PGDATA" -l /var/log/thaum/postgresql/postgres-init.log start -w
gosu postgres /venv/bin/python /app/docker/pg_bootstrap.py
gosu postgres pg_ctl -D "$PGDATA" stop -m fast

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
