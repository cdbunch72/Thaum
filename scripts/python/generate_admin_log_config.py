#!/usr/bin/env python3
# Generate Thaum admin log-level route/secret config artifacts.
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import base64
import secrets
from pathlib import Path


def _b64u_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _new_route_id(length: int = 24) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> int:
    p = argparse.ArgumentParser(description="Generate admin log-level route/secret and config snippets.")
    p.add_argument("--base-url", default="https://thaum.example.com", help="BaseUrl for client profile output")
    p.add_argument("--route-id", help="Optional explicit route id; random generated if omitted")
    p.add_argument("--route-len", type=int, default=24, help="Random route length (default 24)")
    p.add_argument("--secret-file", help="Write HmacSecretB64Url to this file (recommended)")
    p.add_argument("--profile-ini", help="Write client INI profile to this path")
    p.add_argument("--profile-post-url", action="store_true", help="Write PostUrl in profile instead of BaseUrl+RouteId")
    args = p.parse_args()

    route_id = args.route_id or _new_route_id(args.route_len)
    secret_b64u = _b64u_nopad(secrets.token_bytes(32))

    if args.secret_file:
        sf = Path(args.secret_file)
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(secret_b64u + "\n", encoding="utf-8")
        secret_ref = f"file:{sf.as_posix()}"
    else:
        secret_ref = secret_b64u

    if args.profile_ini:
        ini_path = Path(args.profile_ini)
        ini_path.parent.mkdir(parents=True, exist_ok=True)
        if args.profile_post_url:
            content = (
                "[thaum]\n"
                f"PostUrl={args.base_url.rstrip('/')}/{route_id}/log-level\n"
                f"HmacSecretB64Url={secret_b64u}\n"
            )
        else:
            content = (
                "[thaum]\n"
                f"BaseUrl={args.base_url.rstrip('/')}\n"
                f"RouteId={route_id}\n"
                f"HmacSecretB64Url={secret_b64u}\n"
            )
        ini_path.write_text(content, encoding="utf-8")

    print("# --- server [server.admin] snippet (config.toml) ---")
    print("[server.admin]")
    print(f'route_id = "{route_id}"')
    print(f'hmac_secret_b64url = "{secret_ref}"')
    print("clock_skew_seconds = 300")
    print("log_state_poll_seconds = 2.0")
    print()
    print("# --- client profile (INI) ---")
    if args.profile_post_url:
        print("[thaum]")
        print(f"PostUrl={args.base_url.rstrip('/')}/{route_id}/log-level")
        print(f"HmacSecretB64Url={secret_b64u}")
    else:
        print("[thaum]")
        print(f"BaseUrl={args.base_url.rstrip('/')}")
        print(f"RouteId={route_id}")
        print(f"HmacSecretB64Url={secret_b64u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
