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

# region agent log
echo "[debug-131a48][H21] gunicorn exited rc=${rc} attempt=${current_restarts} max=${MAX_RESTARTS} ppid=${PPID}"
# endregion agent log

# Do not clear RESTART_COUNT_FILE on rc=0: gunicorn can exit 0 during flapping and would reset the budget.

if [ "$current_restarts" -ge "$MAX_RESTARTS" ]; then
  # region agent log
  parent_name=""
  if [ -r "/proc/${PPID}/comm" ]; then
    parent_name="$(tr -d '\0' <"/proc/${PPID}/comm")"
  fi
  # In Docker, ``exec supervisord`` makes supervisord PID 1; thaum's parent is then PPID=1 with comm ``supervisord``.
  # On a host, PPID=1 with comm ``systemd`` must never receive SIGTERM from here.
  if [ "$parent_name" = "supervisord" ]; then
    echo "[debug-131a48][H21] restart budget exceeded; sending SIGTERM to supervisord pid=${PPID}"
    kill -TERM "$PPID" 2>/dev/null || true
  else
    echo "[debug-131a48][H21] restart budget exceeded; not signaling parent (ppid=${PPID} comm=${parent_name:-unknown}) — use systemd/orchestrator restart limits"
  fi
  # endregion agent log
  exit 1
fi

exit "$rc"
