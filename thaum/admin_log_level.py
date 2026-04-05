# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/admin_log_level.py
from __future__ import annotations

import base64
import binascii
import hmac
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from flask import Request, jsonify
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from gemstone_utils.db import get_session

from log_setup import (
    mark_db_log_state_applied,
    parse_level_name,
    set_runtime_root_log_level,
)
from thaum.admin_models import ADMIN_LOG_LEVEL_STATE_ID, AdminLogLevelState, AdminLogNonce
from thaum.types import LogLevel, ServerConfig

logger = logging.getLogger("thaum.admin_log_level")

ADMIN_SCHEME = "thaum-log-level-v1"
_ROUTE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")


def admin_hmac_secret_bytes(server: ServerConfig) -> Optional[bytes]:
    raw = os.environ.get("THAUM_LOG_ADMIN_HMAC_SECRET_B64U", "").strip()
    if not raw and server.admin.hmac_secret_b64url:
        raw = str(server.admin.hmac_secret_b64url).strip()
    if not raw:
        return None
    pad = "=" * (-len(raw) % 4)
    try:
        key = base64.urlsafe_b64decode(raw + pad)
    except (binascii.Error, ValueError):
        return None
    if len(key) != 32:
        return None
    return key


def admin_log_routes_enabled(server: ServerConfig) -> bool:
    rid = (server.admin.route_id or "").strip()
    return bool(rid and _ROUTE_ID_RE.match(rid) and admin_hmac_secret_bytes(server))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _parse_iso_utc_epoch_seconds(ts_header: str) -> int:
    s = ts_header.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.astimezone(timezone.utc).timestamp())


def normalize_loglevel_token(raw: str) -> str:
    return raw.strip().upper()


def build_canonical_message(
    *,
    route_id: str,
    epoch_seconds: int,
    nonce_hex: str,
    loglevel_normalized: str,
) -> bytes:
    lines = [
        ADMIN_SCHEME,
        "POST",
        f"/{route_id}/log-level",
        str(epoch_seconds),
        nonce_hex,
        f"loglevel={loglevel_normalized}",
        "v=1",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def verify_signature(key: bytes, message: bytes, sig_header: str) -> bool:
    if not sig_header or not sig_header.startswith("HS256."):
        return False
    encoded = sig_header[6:].strip()
    if not encoded:
        return False
    pad = "=" * (-len(encoded) % 4)
    try:
        expected_raw = base64.urlsafe_b64decode(encoded + pad)
    except (binascii.Error, ValueError):
        return False
    mac = hmac.new(key, message, hashlib.sha256).digest()
    return hmac.compare_digest(mac, expected_raw)


def _allowed_loglevel_name(name: str) -> bool:
    u = name.upper()
    if u == "DEFAULT":
        return True
    return u in LogLevel.__members__


def handle_admin_log_level_post(request: Request, server: ServerConfig) -> Tuple[Any, int]:
    key = admin_hmac_secret_bytes(server)
    route_id = (server.admin.route_id or "").strip()
    if not key or not route_id:
        return jsonify({"error": "not found"}), 404

    ts_header = request.headers.get("X-Thaum-Timestamp", "")
    nonce_header = request.headers.get("X-Thaum-Nonce", "").strip().lower()
    sig_header = request.headers.get("X-Thaum-Signature", "").strip()

    if not ts_header or not nonce_header or not sig_header:
        return jsonify({"error": "unauthorized"}), 401

    if not _NONCE_RE.match(nonce_header):
        return jsonify({"error": "unauthorized"}), 401

    try:
        req_epoch = _parse_iso_utc_epoch_seconds(ts_header)
    except ValueError:
        return jsonify({"error": "unauthorized"}), 401

    now = int(datetime.now(timezone.utc).timestamp())
    skew = int(server.admin.clock_skew_seconds)
    if abs(now - req_epoch) > skew:
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "expected JSON object"}), 400

    if payload.get("v") != 1:
        return jsonify({"error": "bad request"}), 400

    raw_level = payload.get("loglevel")
    if not isinstance(raw_level, str):
        return jsonify({"error": "bad request"}), 400

    norm = normalize_loglevel_token(raw_level)
    if not _allowed_loglevel_name(norm):
        return jsonify({"error": "bad request"}), 400

    canonical_loglevel = "DEFAULT" if norm == "DEFAULT" else norm
    message = build_canonical_message(
        route_id=route_id,
        epoch_seconds=req_epoch,
        nonce_hex=nonce_header,
        loglevel_normalized=canonical_loglevel,
    )

    if not verify_signature(key, message, sig_header):
        return jsonify({"error": "unauthorized"}), 401

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=skew + 120)
    now_dt = datetime.now(timezone.utc)
    db_level: Optional[str] = None if canonical_loglevel == "DEFAULT" else canonical_loglevel

    try:
        with get_session() as session:
            with session.begin():
                session.execute(
                    delete(AdminLogNonce).where(AdminLogNonce.expires_at < now_dt)
                )
                try:
                    with session.begin_nested():
                        session.add(
                            AdminLogNonce(nonce=nonce_header, expires_at=expires_at)
                        )
                        session.flush()
                except IntegrityError:
                    logger.debug("admin log-level nonce replay rejected")
                    return jsonify({"error": "unauthorized"}), 401

                st = session.get(AdminLogLevelState, ADMIN_LOG_LEVEL_STATE_ID)
                if st is None:
                    st = AdminLogLevelState(
                        id=ADMIN_LOG_LEVEL_STATE_ID,
                        log_level=db_level,
                        updated_at=now_dt,
                    )
                    session.add(st)
                else:
                    st.log_level = db_level
                    st.updated_at = now_dt
    except Exception as e:
        logger.warning("admin log-level DB error: %s", e)
        return jsonify({"error": "internal error"}), 500

    if db_level is None:
        set_runtime_root_log_level(None)
    else:
        lv = parse_level_name(db_level)
        set_runtime_root_log_level(lv)

    mark_db_log_state_applied(db_level, now_dt)
    return jsonify({"ok": True}), 200
