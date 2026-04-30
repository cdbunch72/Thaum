# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/paths.py
"""Config file path resolution (shared by app entry and CLI)."""
from __future__ import annotations

import os
from pathlib import Path


class ConfigResolutionError(RuntimeError):
    """Raised when Thaum cannot resolve a startup config path."""


def _candidate_paths(base: Path) -> tuple[Path, ...]:
    """Order: canonical ``thaum.toml`` then ``thaum.conf``."""
    return (
        base / "thaum.toml",
        base / "thaum.conf",
    )


def resolve_config_path() -> str:
    """
    Path to config (TOML in all cases): ``THAUM_CONFIG_FILE`` if set, else the first existing file in order:

    * ``/etc/thaum/`` — ``thaum.toml``, ``thaum.conf``
    * working directory — same basename sequence under ``./``
    """
    env_path = os.environ.get("THAUM_CONFIG_FILE")
    if env_path:
        return env_path

    candidates = (*_candidate_paths(Path("/etc/thaum")), *_candidate_paths(Path(".")))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    checked = ", ".join(str(c) for c in candidates)
    raise ConfigResolutionError(
        "Could not resolve config path. Set THAUM_CONFIG_FILE or create one of: "
        f"{checked}"
    )
