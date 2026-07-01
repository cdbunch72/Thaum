# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/secrets_bootstrap.py
"""One-time gemstone_utils secrets-resolver wiring for Thaum deployments."""
from __future__ import annotations

_wired = False

# Static allowlist only — no runtime env override (see docs / integration notes).
THAUM_FILE_PATH_PREFIXES: tuple[str, ...] = (
    "/etc/thaum",
    "/var/lib/thaum",
    "/app/secret",
)


def wire_gemstone_secrets_resolver() -> None:
    """Configure ``file:`` path allowlist before any config secret resolution."""
    global _wired
    if _wired:
        return
    import sys

    # Allowlist paths are Linux container / FHS mounts; skip on Windows dev hosts.
    if sys.platform == "win32":
        _wired = True
        return
    from gemstone_utils.experimental.secrets_resolver import set_allowed_file_path_prefixes

    set_allowed_file_path_prefixes(list(THAUM_FILE_PATH_PREFIXES))
    _wired = True
