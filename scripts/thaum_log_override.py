#!/usr/bin/env python3
# Thaum — deprecated: runtime log override moved to signed HTTP admin API.
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write(
        "thaum_log_override.py is deprecated.\n"
        "Use scripts/Set-ThaumLogLevel.ps1 (or any HTTP client implementing the scheme in "
        "docs/admin-log-level.md).\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
