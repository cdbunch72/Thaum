#!/usr/bin/env python3
# Thaum signed log-level client (Python).
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import base64
import configparser
import hashlib
import hmac
import json
import re
import secrets
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

ADMIN_SCHEME = "thaum-log-level-v1"
_ROUTE_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")


def _b64u_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + ("=" * (-len(s) % 4)))


def _read_profile(path: str) -> Dict[str, str]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"profile not found: {path}")
    if p.suffix.lower() == ".toml":
        if tomllib is None:
            raise RuntimeError("tomllib not available on this Python version")
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        t = data.get("thaum", {}) if isinstance(data, dict) else {}
        if not isinstance(t, dict):
            return {}
        return {str(k): str(v) for k, v in t.items() if v is not None}
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")
    if cp.has_section("thaum"):
        return {k: v for k, v in cp.items("thaum")}
    return {}


def _normalize_loglevel(raw: str) -> str:
    n = raw.strip().upper()
    return "DEFAULT" if n == "DEFAULT" else n


def _canonical(route_id: str, epoch: int, nonce_hex: str, level: str) -> bytes:
    lines = [
        ADMIN_SCHEME,
        "POST",
        f"/{route_id}/log-level",
        str(epoch),
        nonce_hex,
        f"loglevel={level}",
        "v=1",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _extract_route_from_post_url(post_url: str) -> str:
    from urllib.parse import urlparse

    u = urlparse(post_url)
    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2 or parts[-1] != "log-level":
        raise ValueError("PostUrl path must end with /<RouteId>/log-level")
    return parts[-2]


def _build_request(post_url: str, route_id: str, secret_b64u: str, loglevel_raw: str) -> Tuple[dict, dict]:
    key = _b64u_decode(secret_b64u.strip())
    if len(key) != 32:
        raise ValueError("decoded HMAC key must be 32 bytes")

    nonce = secrets.token_hex(16)
    if not _NONCE_RE.match(nonce):
        raise RuntimeError("internal nonce generation error")

    epoch = int(time.time())
    ts_iso = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    level_norm = _normalize_loglevel(loglevel_raw)

    msg = _canonical(route_id, epoch, nonce, level_norm)
    sig = "HS256." + _b64u_nopad(hmac.new(key, msg, hashlib.sha256).digest())
    headers = {
        "X-Thaum-Timestamp": ts_iso,
        "X-Thaum-Nonce": nonce,
        "X-Thaum-Signature": sig,
        "Content-Type": "application/json",
    }
    body = {"loglevel": loglevel_raw, "v": 1}
    return headers, body


def main() -> int:
    p = argparse.ArgumentParser(
        description="Set Thaum runtime root log level using signed POST (docs/admin-log-level.md)."
    )
    p.add_argument("loglevel", help="Target level (e.g. DEBUG, INFO, default)")
    p.add_argument("--profile", help="INI or TOML profile file with [thaum] values")
    p.add_argument("--secret-b64url", dest="secret", help="Override HmacSecretB64Url")
    p.add_argument("--base-url", help="Override BaseUrl")
    p.add_argument("--route-id", help="Override RouteId")
    p.add_argument("--post-url", help="Override PostUrl")
    args = p.parse_args()

    cfg: Dict[str, str] = {}
    if args.profile:
        cfg = _read_profile(args.profile)

    base_url = args.base_url or cfg.get("BaseUrl") or cfg.get("baseurl", "")
    route_id = args.route_id or cfg.get("RouteId") or cfg.get("routeid", "")
    secret = args.secret or cfg.get("HmacSecretB64Url") or cfg.get("hmacsecretb64url", "")
    post_url = args.post_url or cfg.get("PostUrl") or cfg.get("posturl", "")

    if not secret:
        raise SystemExit("HmacSecretB64Url is required (profile or --secret-b64url).")

    if post_url:
        route_for_sign = _extract_route_from_post_url(post_url)
        final_url = post_url
    else:
        if not base_url or not route_id:
            raise SystemExit("Need PostUrl or both BaseUrl and RouteId.")
        if not _ROUTE_RE.match(route_id):
            raise SystemExit("RouteId is invalid (expected 8-128 chars [A-Za-z0-9_-]).")
        route_for_sign = route_id
        final_url = f"{base_url.rstrip('/')}/{route_id}/log-level"

    headers, body = _build_request(final_url, route_for_sign, secret, args.loglevel)
    req = urllib.request.Request(
        final_url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(req) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        if text.strip():
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
