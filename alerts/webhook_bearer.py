# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/webhook_bearer.py
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Mapping, Optional, Tuple, cast

import hmac

# At most one rotation-window warning per token per interval (avoid log spam on every webhook).
# Throttle state lives only in ``webhook_bearer_warn_state`` (requires initialized DB).
_CLEANUP_EXPIRED_BEFORE = timedelta(days=1)
_ROTATION_WARN_INTERVAL_SEC: float = 86400.0


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


__all__ = [
    "canonical_alert_bearer_bytes",
    "parse_incoming_bearer_payload",
    "normalize_expected_secret_to_canonical_bytes",
    "validate_webhook_bearer",
]


class _RotationThrottleResult(Enum):
    EMIT = auto()
    SUPPRESS = auto()
    STORAGE_FAILED = auto()


def canonical_alert_bearer_bytes(d: Mapping[str, Any]) -> bytes:
    """
    Canonical UTF-8 JSON for the bearer record after coercing numeric fields,
    so 30 and 30.0 serialize identically and compare safely.
    """
    for k in ("iat", "exp", "warn", "key"):
        if k not in d:
            raise ValueError(f"webhook bearer payload missing required key: {k}")

    iat = int(d["iat"])
    exp_v = d["exp"]
    if exp_v is None:
        exp = None
    else:
        exp = int(exp_v)
    warn = int(d["warn"])
    key = str(d["key"])
    if not key:
        raise ValueError("key must be a non-empty string")

    return json.dumps(
        {"exp": exp, "iat": iat, "key": key, "warn": warn},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _strip_bearer_prefix(header_value: str) -> str:
    v = header_value.strip()
    if v.lower().startswith("bearer "):
        return v[7:].strip()
    return v


def _b64url_decode_padded(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _try_decode_bearer_blob(blob: str) -> Tuple[dict[str, Any], bytes]:
    """
    Decode Bearer value to (parsed dict, canonical UTF-8 bytes).
    Accepts either base64url(UTF-8 canonical/minimal JSON) or raw JSON string.
    """
    blob = blob.strip()
    text: str
    try:
        raw = _b64url_decode_padded(blob)
        text = raw.decode("utf-8")
        obj = json.loads(text)
    except Exception:
        text = blob
        obj = json.loads(text)

    if not isinstance(obj, dict):
        raise ValueError("webhook bearer payload must be a JSON object")

    d = cast(dict[str, Any], obj)
    canonical = canonical_alert_bearer_bytes(d)
    return d, canonical


def parse_incoming_bearer_payload(header_value: str) -> Tuple[dict[str, Any], bytes]:
    """
    Parse Authorization header value (with or without 'Bearer ' prefix).
    Returns (parsed dict, canonical_json_bytes) for constant-time compare.
    """
    blob = _strip_bearer_prefix(header_value)
    d, canonical = _try_decode_bearer_blob(blob)
    return d, canonical


def normalize_expected_secret_to_canonical_bytes(expected_secret: str) -> bytes:
    """
    Normalize configured secret to canonical JSON bytes.
    If the secret is JSON (object), re-canonicalize; otherwise treat as literal UTF-8
    (must match incoming canonical bytes exactly).
    """
    raw = expected_secret.strip()
    if not raw:
        raise ValueError("webhook bearer secret is empty")

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return raw.encode("utf-8")

    if not isinstance(obj, dict):
        raise ValueError("webhook bearer secret JSON must be a JSON object")
    d = cast(dict[str, Any], obj)
    return canonical_alert_bearer_bytes(d)


def _warn_cache_key(canonical_bytes: bytes) -> str:
    return hashlib.sha256(canonical_bytes).hexdigest()
# -- End Function _warn_cache_key


def _db_throttle_should_log(
    logger: logging.Logger,
    token_fp: str,
    *,
    expires_at_utc: datetime,
    bot_key: Optional[str],
) -> _RotationThrottleResult:
    """
    Return EMIT if a rotation warning may be logged (and record throttle in DB).
    Return SUPPRESS if within the interval.
    Return STORAGE_FAILED if the DB path failed (caller should not emit rotation warning).
    """
    try:
        from sqlalchemy import delete
        from sqlalchemy.exc import IntegrityError

        from gemstone_utils.db import get_session

        from thaum.webhook_bearer_warn import WebhookBearerWarnState
    except Exception as e:
        from log_setup import should_log_exception_trace

        logger.warning(
            "Webhook bearer rotation throttle skipped: could not load DB layer (transient)."
        )
        logger.error(
            "Webhook bearer rotation throttle: import or setup failed: %s",
            e,
            exc_info=should_log_exception_trace(),
        )
        return _RotationThrottleResult.STORAGE_FAILED

    now_dt = datetime.now(timezone.utc)
    cleanup_before = now_dt - _CLEANUP_EXPIRED_BEFORE

    try:
        with get_session() as session:
            with session.begin():
                session.execute(
                    delete(WebhookBearerWarnState).where(
                        WebhookBearerWarnState.expires_at.isnot(None),
                        WebhookBearerWarnState.expires_at < cleanup_before,
                    )
                )
                row = session.get(WebhookBearerWarnState, token_fp)
                if row is not None:
                    age_sec = (now_dt - _as_utc_aware(row.last_warn_at)).total_seconds()
                    if age_sec < _ROTATION_WARN_INTERVAL_SEC:
                        return _RotationThrottleResult.SUPPRESS
                    row.last_warn_at = now_dt
                    row.expires_at = expires_at_utc
                    if bot_key is not None:
                        row.bot_key = bot_key
                    return _RotationThrottleResult.EMIT

                new_row = WebhookBearerWarnState(
                    token_fp=token_fp,
                    last_warn_at=now_dt,
                    expires_at=expires_at_utc,
                    bot_key=bot_key,
                )
                try:
                    with session.begin_nested():
                        session.add(new_row)
                        session.flush()
                except IntegrityError:
                    row2 = session.get(WebhookBearerWarnState, token_fp)
                    if row2 is None:
                        return _RotationThrottleResult.EMIT
                    age2 = (now_dt - _as_utc_aware(row2.last_warn_at)).total_seconds()
                    if age2 < _ROTATION_WARN_INTERVAL_SEC:
                        return _RotationThrottleResult.SUPPRESS
                    row2.last_warn_at = now_dt
                    row2.expires_at = expires_at_utc
                    if bot_key is not None:
                        row2.bot_key = bot_key
                    return _RotationThrottleResult.EMIT
                return _RotationThrottleResult.EMIT
    except Exception as e:
        from log_setup import should_log_exception_trace

        logger.warning(
            "Webhook bearer rotation throttle skipped: database error (transient)."
        )
        logger.error(
            "Webhook bearer rotation throttle failed: %s",
            e,
            exc_info=should_log_exception_trace(),
        )
        return _RotationThrottleResult.STORAGE_FAILED
# -- End Function _db_throttle_should_log


def _maybe_log_rotation_warning(
    logger: logging.Logger,
    *,
    canonical_bytes: bytes,
    warn_days: int,
    exp_t: float,
    bot_key: Optional[str] = None,
) -> None:
    cache_key = _warn_cache_key(canonical_bytes)
    expires_at_utc = datetime.fromtimestamp(exp_t, tz=timezone.utc)

    db_res = _db_throttle_should_log(
        logger,
        cache_key,
        expires_at_utc=expires_at_utc,
        bot_key=bot_key,
    )
    if db_res is _RotationThrottleResult.SUPPRESS:
        return
    if db_res is _RotationThrottleResult.STORAGE_FAILED:
        return
    logger.warning(
        "Webhook bearer token is inside the %d-day pre-expiry window (expires at %d); "
        "rotate soon. (At most once per day per token; throttle in DB table "
        "webhook_bearer_warn_state.)",
        warn_days,
        int(exp_t),
    )
# -- End Function _maybe_log_rotation_warning


def validate_webhook_bearer(
    *,
    authorization_header_value: Optional[str],
    expected_secret_text: str,
    logger: logging.Logger,
    bot_key: Optional[str] = None,
) -> bool:
    """
    Constant-time compare of canonical JSON bytes after parsing incoming Bearer value.
    Enforces exp (null = never). When within ``warn`` days of exp, logs a warning at most
    once per 24 hours per token; throttle state is stored only in the
    ``webhook_bearer_warn_state`` table. If the database cannot be used, logs WARNING and
    ERROR (stack traces only when root log level enables SPAM) and does not emit the
    pre-expiry advisory.

    ``bot_key`` is optional metadata stored with the throttle row (not used for auth).
    """
    if not authorization_header_value:
        logger.warning("Webhook request missing Authorization bearer value.")
        return False

    try:
        parsed, incoming_canonical = parse_incoming_bearer_payload(authorization_header_value)
    except Exception as e:
        logger.warning("Webhook bearer parse failed: %s", e)
        return False

    try:
        expected_canonical = normalize_expected_secret_to_canonical_bytes(expected_secret_text)
    except Exception as e:
        logger.error("Invalid webhook bearer secret configuration: %s", e)
        return False

    if not hmac.compare_digest(incoming_canonical, expected_canonical):
        logger.warning("Webhook bearer token mismatch (canonical JSON).")
        return False

    exp = parsed.get("exp")
    if exp is not None:
        exp_t = float(exp)
        if time.time() > exp_t:
            logger.warning("Webhook bearer token expired.")
            return False

        warn_days = int(parsed.get("warn", 0))
        if warn_days > 0:
            warn_before = exp_t - warn_days * 86400.0
            if time.time() >= warn_before:
                _maybe_log_rotation_warning(
                    logger,
                    canonical_bytes=incoming_canonical,
                    warn_days=warn_days,
                    exp_t=exp_t,
                    bot_key=bot_key,
                )

    return True
# -- End Function validate_webhook_bearer
