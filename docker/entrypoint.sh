#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
set -e

# So gunicorn (and similar) do not use /root when dropping to user thaum via gosu/supervisor.
export HOME=/home/thaum

# Systemd/orchestrator credentials often appear under /run/secrets (or /var/run/secrets) with
# permissions readable only by root. The app runs as user thaum, so resolve_secret(secret:...)
# cannot read those files unless we copy them to a tmpfs dir (see Quadlet THAUM_CREDS_DIR) and
# point CREDENTIALS_DIRECTORY there. This must run before any exec path (external DB or supervisord).
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
mkdir -p /var/log/thaum/postgresql /var/log/supervisor
install -d -m 0750 -o postgres -g postgres /tmp/postgres
chown postgres:postgres /var/log/thaum/postgresql
mkdir -p "$PGDATA"
chown postgres:postgres "$PGDATA"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  gosu postgres initdb -D "$PGDATA"
  cat > "$PGDATA/postgresql.auto.conf" <<'EOF'
listen_addresses = ''
unix_socket_directories = '/tmp/postgres'
EOF
  touch "$PGDATA/.thaum_configured"
elif [ ! -f "$PGDATA/.thaum_configured" ]; then
  cat > "$PGDATA/postgresql.auto.conf" <<'EOF'
listen_addresses = ''
unix_socket_directories = '/tmp/postgres'
EOF
  touch "$PGDATA/.thaum_configured"
fi
# Legacy clusters: socket was under /run/thaum/postgres (parent dir perms broke some hosts).
if [ -f "$PGDATA/postgresql.auto.conf" ] && grep -Fq "unix_socket_directories = '/run/thaum/postgres'" "$PGDATA/postgresql.auto.conf"; then
  sed -i "s|unix_socket_directories = '/run/thaum/postgres'|unix_socket_directories = '/tmp/postgres'|" "$PGDATA/postgresql.auto.conf"
fi

gosu postgres pg_ctl -D "$PGDATA" -l /var/log/thaum/postgresql/postgres-init.log start -w
gosu postgres /venv/bin/python /app/docker/pg_bootstrap.py
gosu postgres pg_ctl -D "$PGDATA" stop -m fast

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
