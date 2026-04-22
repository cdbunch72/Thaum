#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
set -e
/app/docker/wait_for_pg.sh

# region agent log
RESTART_COUNT_FILE="${THAUM_RESTART_COUNT_FILE:-/tmp/thaum-gunicorn-restarts}"
MAX_RESTARTS="${THAUM_MAX_RESTARTS:-5}"

current_restarts=0
if [ -f "$RESTART_COUNT_FILE" ]; then
  current_restarts="$(cat "$RESTART_COUNT_FILE" 2>/dev/null || echo 0)"
fi
case "$current_restarts" in
  ''|*[!0-9]*) current_restarts=0 ;;
esac
current_restarts=$((current_restarts + 1))
echo "$current_restarts" > "$RESTART_COUNT_FILE"
echo "[debug-131a48][H21] run_thaum start attempt=${current_restarts} max=${MAX_RESTARTS} ppid=${PPID}"
# endregion agent log

set +e
/venv/bin/gunicorn \
  --bind "${GUNICORN_BIND:-0.0.0.0:5165}" \
  --workers "${GUNICORN_WORKERS:-1}" \
  app:app
rc="$?"
set -e

if [ "$rc" -eq 0 ]; then
  rm -f "$RESTART_COUNT_FILE"
  exit 0
fi

# region agent log
echo "[debug-131a48][H21] gunicorn exited rc=${rc} attempt=${current_restarts} max=${MAX_RESTARTS}"
if [ "$current_restarts" -ge "$MAX_RESTARTS" ]; then
  echo "[debug-131a48][H21] restart budget exceeded; terminating supervisord pid=${PPID}"
  kill -TERM "$PPID" 2>/dev/null || true
fi
# endregion agent log

exit "$rc"
