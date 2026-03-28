# app.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

"""
WSGI entry: ``gunicorn app:app`` (set ``THAUM_CONFIG`` or default ``config.toml``).
"""

from __future__ import annotations

import os

from bootstrap import bootstrap
from web import create_app

_config_path = os.environ.get("THAUM_CONFIG", "config.toml")
_config = bootstrap(_config_path)
app = create_app(_config)

if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_RUN_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes"),
    )
