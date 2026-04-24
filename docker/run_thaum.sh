#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
set -e
/app/docker/wait_for_pg.sh

RESTART_COUNT_FILE="${THAUM_RESTART_COUNT_FILE:-/tmp/thaum-gunicorn-restarts}"
MAX_RESTARTS="${THAUM_MAX_RESTARTS:-5}"

_signal_supervisord_if_budget_exceeded() {
  parent_name=""
  if [ -r "/proc/${PPID}/comm" ]; then
    parent_name="$(tr -d '\0' <"/proc/${PPID}/comm")"
  fi
  if [ "$parent_name" = "supervisord" ]; then
    echo "run_thaum: restart budget exceeded; sending SIGTERM to supervisord pid=${PPID}"
    kill -TERM "$PPID" 2>/dev/null || true
  else
    echo "run_thaum: restart budget exceeded; not signaling parent (ppid=${PPID} comm=${parent_name:-unknown}) — use systemd/orchestrator restart limits"
  fi
}

n=0
if [ -f "$RESTART_COUNT_FILE" ]; then
  n="$(cat "$RESTART_COUNT_FILE" 2>/dev/null || echo 0)"
fi
case "$n" in
  ''|*[!0-9]*) n=0 ;;
esac

# Already at or past budget: do not increment again; stop supervisord / fail fast.
if [ "$n" -ge "$MAX_RESTARTS" ]; then
  echo "run_thaum: budget already exhausted (count=${n} max=${MAX_RESTARTS}) ppid=${PPID}"
  _signal_supervisord_if_budget_exceeded
  exit 1
fi

n=$((n + 1))
echo "$n" >"$RESTART_COUNT_FILE"
echo "run_thaum: start attempt=${n} max=${MAX_RESTARTS} ppid=${PPID}"

set +e
/venv/bin/gunicorn \
  --bind "${GUNICORN_BIND:-0.0.0.0:5165}" \
  --workers "${GUNICORN_WORKERS:-1}" \
  app:app
rc="$?"
set -e

echo "run_thaum: gunicorn exited rc=${rc} attempt=${n} max=${MAX_RESTARTS} ppid=${PPID}"

if [ "$rc" -eq 0 ]; then
  rm -f "$RESTART_COUNT_FILE"
  exit 0
fi

if [ "$n" -ge "$MAX_RESTARTS" ]; then
  _signal_supervisord_if_budget_exceeded
  exit 1
fi

exit "$rc"
