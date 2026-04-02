# app.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

"""
WSGI entry: ``gunicorn --workers 1 app:app`` (use one worker until leader election exists for
Spark webhook registration). Config: ``THAUM_CONFIG_FILE``, else ``/etc/thaum/thaum.conf`` or
``thaum.toml`` in the working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from bootstrap import bootstrap
from web import create_app

def _resolve_config_path() -> str:
    env_path = os.environ.get("THAUM_CONFIG_FILE")
    if env_path:
        return env_path

    candidates = (
        Path("/etc/thaum/thaum.conf"),
        Path("./thaum.toml"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    # Fall back to default in the current directory if no known file exists.
    return "thaum.toml"


_config = bootstrap(_resolve_config_path())
app = create_app(_config)

if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_RUN_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes"),
    )
