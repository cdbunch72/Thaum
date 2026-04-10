# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# app.py
"""
WSGI entry: ``gunicorn app:app`` (multiple workers supported: leader election registers Webex
webhooks once per deployment). Set ``server.database.database_vault_passphrase`` when using shared DB
Webex HMAC (omit ``hmac_secret`` in bot config). Config: ``THAUM_CONFIG_FILE``, else
``/etc/thaum/thaum.conf`` or ``thaum.toml`` in the working directory.
"""

from __future__ import annotations

import os

from bootstrap import bootstrap
from thaum.paths import resolve_config_path
from web import create_app

_config = bootstrap(resolve_config_path())
app = create_app(_config)

if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_RUN_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes"),
    )
