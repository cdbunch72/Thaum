# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/paths.py
"""Config file path resolution (shared by app entry and CLI)."""
from __future__ import annotations

import os
from pathlib import Path


def resolve_config_path() -> str:
    """
    Path to TOML config: ``THAUM_CONFIG_FILE``, else first existing
    ``/etc/thaum/thaum.conf`` or ``./thaum.toml``, else ``thaum.toml`` in the working directory.
    """
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

    return "thaum.toml"
