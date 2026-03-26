# server.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

"""
Process bootstrap for HTTP services.

Call :func:`bootstrap_thaum` (or :func:`load_and_validate` + :func:`initialize_runtime_plugins`)
before importing application code that touches the DB: lookup ORM tables are created by
:func:`emerald_utils.db.init_db`, invoked from :func:`lookup.db_bootstrap.init_lookup_db`.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict

from config import initialize_runtime_plugins, load_and_validate


def bootstrap_thaum(config_path: str) -> Dict[str, Any]:
    """
    Load ``config.toml``, open the shared EmeraldDB engine, then initialize runtime plugins
    (lookup, webhook state dir, etc.).
    """
    config = load_and_validate(config_path)
    initialize_runtime_plugins(config)
    return config


def main() -> None:
    p = argparse.ArgumentParser(description="Thaum server bootstrap (config + DB + plugins).")
    p.add_argument(
        "config",
        nargs="?",
        default=os.environ.get("THAUM_CONFIG", "config.toml"),
        help="Path to config.toml (default: $THAUM_CONFIG or ./config.toml)",
    )
    args = p.parse_args()
    bootstrap_thaum(args.config)


if __name__ == "__main__":
    main()
