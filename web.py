# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# web.py
from __future__ import annotations

import json
import logging
import os
import time
import traceback
from typing import Any, Dict

from flask import Flask, jsonify, request
from gemstone_utils.db import get_session
from sqlalchemy import text

from thaum.admin_log_level import admin_log_routes_enabled, handle_admin_log_level_post
from thaum.database_crypto import apply_database_crypto
from thaum.bots_registry import BOTS
from thaum.leader_service import start_leader_loop
from thaum.types import ServerConfig
from thaum.types import LogLevel
from log_setup import log_debug_blob

logger = logging.getLogger("thaum.web")

# region agent log
def _agent_dbg_web(hypothesis_id: str, location: str, message: str, data: Dict[str, Any]) -> None:
    logger.warning(
        "[debug-131a48][%s] %s: %s data=%s",
        hypothesis_id,
        location,
        message,
        data,
    )
    try:
        os.makedirs("/var/log/thaum", exist_ok=True)
        with open("/var/log/thaum/debug-131a48.log", "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "131a48",
                        "timestamp": int(time.time() * 1000),
                        "runId": "http-webhook",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                    }
                )
                + "\n"
            )
    except Exception:
        pass


# endregion agent log


def create_app(config: Dict[str, Any], *, run_leader_loop: bool = True) -> Flask:
    """Flask application factory; expects ``bootstrap()`` to have run first."""
    app = Flask(__name__)
    app.config["THAUM"] = config

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.get("/ready")
    def ready():
        try:
            with get_session() as session:
                session.execute(text("SELECT 1"))
        except Exception as e:
            logger.warning("Readiness check failed: %s", e)
            return jsonify({"status": "unavailable", "reason": "database"}), 503
        return jsonify({"status": "ok"}), 200

    @app.post("/bot/<bot_key>")
    def bot_webhook(bot_key: str):
        # region agent log
        try:
            clen = request.content_length
        except Exception:
            clen = None
        _agent_dbg_web(
            "H13",
            "web.py:bot_webhook:entry",
            "POST /bot/<bot_key> received",
            {
                "bot_key": bot_key,
                "content_length": clen,
                "has_x_spark_signature": bool(request.headers.get("X-Spark-Signature")),
                "registered_bot_keys": sorted(BOTS.keys()),
            },
        )
        # endregion agent log
        bot = BOTS.get(bot_key)
        if bot is None:
            logger.log(
                LogLevel.DEBUG,
                "unknown bot_key=%r for POST /bot; registered keys: %s",
                bot_key,
                sorted(BOTS.keys()),
            )
            # region agent log
            _agent_dbg_web(
                "H13",
                "web.py:bot_webhook:unknown_bot",
                "unknown bot_key",
                {"bot_key": bot_key, "registered_bot_keys": sorted(BOTS.keys())},
            )
            # endregion agent log
            return jsonify({"error": "unknown bot"}), 404
        try:
            if not bot.authenticate_request(request):
                # region agent log
                _agent_dbg_web(
                    "H14",
                    "web.py:bot_webhook:auth_failed",
                    "authenticate_request returned False",
                    {"bot_key": bot_key, "plugin": getattr(bot, "plugin_name", None)},
                )
                # endregion agent log
                return jsonify({"error": "unauthorized"}), 401
        except Exception as e:
            logger.warning("Bot auth error for %s: %s", bot_key, e)
            # region agent log
            _agent_dbg_web(
                "H14",
                "web.py:bot_webhook:auth_exception",
                "authenticate_request raised",
                {"bot_key": bot_key, "error": type(e).__name__},
            )
            # endregion agent log
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(force=True, silent=True)
        if not isinstance(payload, dict):
            # region agent log
            _agent_dbg_web(
                "H15",
                "web.py:bot_webhook:bad_json",
                "request body was not a JSON object",
                {"bot_key": bot_key, "payload_type": type(payload).__name__},
            )
            # endregion agent log
            return jsonify({"error": "expected JSON object"}), 400
        # region agent log
        _agent_dbg_web(
            "H15",
            "web.py:bot_webhook:before_handle_event",
            "auth ok, dispatching handle_event",
            {
                "bot_key": bot_key,
                "resource": payload.get("resource"),
                "has_data": isinstance(payload.get("data"), dict),
            },
        )
        # endregion agent log
        try:
            bot.handle_event(payload)
        except Exception as e:
            logger.error("handle_event failed for bot %s: %s", bot_key, e)
            # region agent log
            _agent_dbg_web(
                "H15",
                "web.py:bot_webhook:handle_event_exception",
                "handle_event raised",
                {"bot_key": bot_key, "error": type(e).__name__},
            )
            # endregion agent log
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(logger, f"handle_event traceback (bot={bot_key})", traceback.format_exc(), LogLevel.SPAM)
            return jsonify({"error": "internal error"}), 500
        # region agent log
        _agent_dbg_web(
            "H15",
            "web.py:bot_webhook:success",
            "handle_event completed",
            {"bot_key": bot_key},
        )
        # endregion agent log
        return "", 204

    server: ServerConfig = config["server"]
    apply_database_crypto(server)
    if admin_log_routes_enabled(server):
        route_id = server.admin.route_id.strip()

        @app.post(f"/{route_id}/log-level", endpoint="thaum_admin_log_level")
        def admin_log_level():
            return handle_admin_log_level_post(request, server)

    @app.post("/alerts/<bot_key>/status")
    def alert_status_webhook(bot_key: str):
        bot = BOTS.get(bot_key)
        if bot is None:
            logger.log(
                LogLevel.DEBUG,
                "unknown bot_key=%r for POST /alerts/.../status; registered keys: %s",
                bot_key,
                sorted(BOTS.keys()),
            )
            return jsonify({"error": "unknown bot"}), 404
        plugin = getattr(bot, "alert_plugin", None)
        if plugin is None or not getattr(plugin, "supports_status_webhooks", False):
            return jsonify({"error": "not found"}), 404
        auth = request.headers.get("Authorization")
        try:
            if not plugin.validate_status_webhook_authorization(auth):
                return jsonify({"error": "unauthorized"}), 401
        except Exception as e:
            logger.warning("Alert status auth error for %s: %s", bot_key, e)
            return jsonify({"error": "unauthorized"}), 401
        payload = request.get_json(force=True, silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "expected JSON object"}), 400
        try:
            plugin.handle_status_webhook(payload)
        except Exception as e:
            logger.error("alert status webhook handler failed for bot %s: %s", bot_key, e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(
                    logger,
                    f"alert status webhook traceback (bot={bot_key})",
                    traceback.format_exc(),
                    LogLevel.SPAM,
                )
        return "", 204

    leader_cid = config.pop("_thaum_leader_candidate_id", None)
    start_leader_loop(
        server,
        config,
        candidate_id=leader_cid,
        run_leader_loop=run_leader_loop,
    )
    return app
# -- End Function create_app