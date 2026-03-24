#!/usr/bin/env python3
# Thaum — companion CLI for runtime log level override (/run/thaum/log_override).
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import os
import sys

# Allow running without installing the package (repo root on path).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from log_setup import LOG_OVERRIDE_PATH, parse_level_name  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manage Thaum log override file for workers."
        )
    )
    parser.add_argument(
        "command",
        metavar="LEVEL|default",
        help="Logging level name (e.g. DEBUG, INFO, SPAM) or 'default' to remove override.",
    )
    parser.add_argument(
        "--path",
        default=LOG_OVERRIDE_PATH,
        help=f"Override file path (default: {LOG_OVERRIDE_PATH})",
    )
    args = parser.parse_args()
    raw = args.command.strip()
    path = args.path

    if raw.lower() == "default":
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"error: could not remove {path}: {e}", file=sys.stderr)
            return 1
        print(f"removed {path} (workers will restore configured level on the next reload)")
        return 0

    level = parse_level_name(raw)
    if level is None:
        print(f"error: unknown log level {raw!r}", file=sys.stderr)
        return 1

    parent = os.path.dirname(path)
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as e:
        print(f"error: could not create {parent}: {e}", file=sys.stderr)
        return 1

    try:
        # Atomic update: write to temp file in same directory, then replace.
        parent = os.path.dirname(path)
        tmp_path = os.path.join(parent, f".log_override.tmp.{os.getpid()}")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(raw.strip().upper() + "\n")
        os.replace(tmp_path, path)
    except OSError as e:
        print(f"error: could not write {path}: {e}", file=sys.stderr)
        return 1

    print(f"wrote {path} -> {raw.strip().upper()}")
    print(
        "workers will reload automatically if your [server] config has: "
        "`log_override_poll_seconds` > 0 for polling (default is enabled), "
        "or `log_override_watchdog=true` if you also run with `watchdog` installed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
