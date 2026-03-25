#!/usr/bin/env python3
# generate_webhook_bearer_token.py
# Copyright 2026 Clinton Bunch. All rights reserved.
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

"""
Generate a canonical JSON webhook bearer record for Thaum alert status webhooks.

Fields:
  iat  — issued-at (Unix seconds)
  exp  — expiry (Unix seconds) or null for never
  warn — days before exp to log a rotation warning (ignored when exp is null)
  key  — random key (base64url, 16 bytes / 128-bit), no padding

Output:
  1) Canonical JSON (store in config / secrets for the plugin's bearer field, e.g. status_webhook_bearer)
  2) Optional Bearer line using base64url(canonical UTF-8 bytes) for header-only configs
"""

from __future__ import annotations

import argparse
import base64
import secrets
import sys
import time
from pathlib import Path

# Run as script: allow repo root on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alerts.webhook_bearer import canonical_alert_bearer_bytes  # noqa: E402


def _b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _parse_expire(value: str) -> int | None:
    """Days from now (non-negative int), or None for never."""
    v = value.strip().lower()
    if v == "never":
        return None
    try:
        n = int(v, 10)
        if n < 0:
            raise ValueError
        return n
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            "expire must be a non-negative integer (days) or the word never"
        ) from e


def main() -> None:
    p = argparse.ArgumentParser(description="Generate Thaum webhook bearer token JSON.")
    p.add_argument(
        "--warn-days",
        type=int,
        default=30,
        help="Days before exp to warn (logged at webhook validation). Default: 30",
    )
    p.add_argument(
        "--expire",
        type=_parse_expire,
        default=_parse_expire("180"),
        help='Days from now until exp, or "never". Default: 180',
    )
    p.add_argument(
        "--include-bearer-line",
        action="store_true",
        help="Also print a line suitable for Authorization: Bearer <...>",
    )
    args = p.parse_args()

    iat = int(time.time())
    expire_spec = args.expire
    if expire_spec is None:
        exp = None
    else:
        exp = int(iat + expire_spec * 86400)

    key = _b64url_nopad(secrets.token_bytes(16))
    payload = {
        "exp": exp,
        "iat": iat,
        "key": key,
        "warn": int(args.warn_days),
    }
    canonical = canonical_alert_bearer_bytes(payload)
    text = canonical.decode("utf-8")

    print(text)
    if args.include_bearer_line:
        wire = _b64url_nopad(canonical)
        print(f"Authorization: Bearer {wire}")


if __name__ == "__main__":
    main()
