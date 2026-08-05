# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/https_url.py
"""Validate and normalize https base URLs used as HTTP client prefixes."""
from __future__ import annotations

from urllib.parse import urlparse


def normalize_https_base_url(url: str) -> str:
    """
    Require an ``https`` URL with a hostname and no embedded credentials.

    Returns the stripped URL with a trailing slash removed.
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL must be a non-empty https URL")

    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"URL must use https scheme, got {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not include username or password")

    return raw.rstrip("/")
