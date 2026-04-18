# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/http_timeouts.py
"""
Shared ``requests`` timeout tuples: ``(connect, read)``.

A short **fractional** connect timeout fails fast when the endpoint is unreachable; the read
phase may be longer for JSON bodies. This split also plays well with TCP backoff behavior.
"""
from __future__ import annotations

# Seconds to establish TCP/TLS (fractional values are valid for ``requests``).
HTTP_CONNECT_TIMEOUT: float = 2.5


def timeout_pair(read_seconds: float) -> tuple[float, float]:
    """Return ``(HTTP_CONNECT_TIMEOUT, read_seconds)`` for passing to ``requests`` ``timeout=``."""
    return (HTTP_CONNECT_TIMEOUT, float(read_seconds))
