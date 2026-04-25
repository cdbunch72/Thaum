# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/paths.py
"""Config file path resolution (shared by app entry and CLI)."""
from __future__ import annotations

import os
from pathlib import Path


def _candidate_paths(base: Path) -> tuple[Path, ...]:
    """Order: title-case ``Thaum`` stem, then lowercase ``thaum``, ``.toml`` before ``.conf``; then ``config``."""
    return (
        base / "Thaum.toml",
        base / "Thaum.conf",
        base / "thaum.toml",
        base / "thaum.conf",
        base / "config.toml",
        base / "config.conf",
    )


def resolve_config_path() -> str:
    """
    Path to config (TOML in all cases): ``THAUM_CONFIG_FILE`` if set, else the first existing file in order:

    * ``/etc/thaum/`` — ``Thaum.toml``, ``Thaum.conf``, ``thaum.toml``, ``thaum.conf``, ``config.toml``, ``config.conf``
    * working directory — same basename sequence under ``./``

    If none exist, returns ``thaum.toml`` (typical path for a new file in the working directory).
    """
    env_path = os.environ.get("THAUM_CONFIG_FILE")
    if env_path:
        return env_path

    candidates = (*_candidate_paths(Path("/etc/thaum")), *_candidate_paths(Path(".")))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return "thaum.toml"
