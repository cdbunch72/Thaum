# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# web.py
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict

from flask import Flask, jsonify, request
from gemstone_utils.db import get_session
from sqlalchemy import text

from thaum.admin_log_level import admin_log_routes_enabled, handle_admin_log_level_post
from thaum.database_crypto import apply_database_crypto
from thaum.factory import BOTS
from thaum.leader_service import start_leader_loop
from thaum.types import ServerConfig
from thaum.types import LogLevel
from log_setup import log_debug_blob

logger = logging.getLogger("thaum.web")


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
        bot = BOTS.get(bot_key)
        if bot is None:
            return jsonify({"error": "unknown bot"}), 404
        try:
            if not bot.authenticate_request(request):
                return jsonify({"error": "unauthorized"}), 401
        except Exception as e:
            logger.warning("Bot auth error for %s: %s", bot_key, e)
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(force=True, silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "expected JSON object"}), 400
        try:
            bot.handle_event(payload)
        except Exception as e:
            logger.error("handle_event failed for bot %s: %s", bot_key, e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(logger, f"handle_event traceback (bot={bot_key})", traceback.format_exc(), LogLevel.SPAM)
            return jsonify({"error": "internal error"}), 500
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

    start_leader_loop(server, config, run_leader_loop=run_leader_loop)
    return app
# -- End Function create_app