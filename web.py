# web.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import Flask, jsonify, request

from thaum.admin_log_level import admin_log_routes_enabled, handle_admin_log_level_post
from thaum.factory import BOTS, register_all_bot_webhooks
from thaum.types import ServerConfig

logger = logging.getLogger("thaum.web")


def create_app(config: Dict[str, Any]) -> Flask:
    """Flask application factory; expects ``bootstrap()`` to have run first."""
    app = Flask(__name__)
    app.config["THAUM"] = config

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
            logger.exception("handle_event failed for bot %s: %s", bot_key, e)
            return jsonify({"error": "internal error"}), 500
        return "", 204

    server: ServerConfig = config["server"]
    if admin_log_routes_enabled(server):
        route_id = server.log_admin_route_id.strip()

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
            logger.exception("alert status webhook handler failed for bot %s: %s", bot_key, e)
        return "", 204

    register_all_bot_webhooks()
    return app
# -- End Function create_app
