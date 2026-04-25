#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
set -e

/app/docker/wait_for_pg.sh

exec /venv/bin/gunicorn \
  --bind "${GUNICORN_BIND:-0.0.0.0:5165}" \
  --workers "${GUNICORN_WORKERS:-1}" \
  app:app
