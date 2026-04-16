# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/factory.py
from __future__ import annotations

import logging
from typing import Any, Dict

from bots.factory import create_bot_from_model
from lookup.instance import get_lookup_plugin
from plugin_loader import get_plugin
from thaum.bots_registry import BOTS
from thaum.handlers import bind_thaum_handlers
from thaum.types import LogLevel, ThaumPerson, RespondersList


def register_all_bot_webhooks() -> None:
    """Call after Flask (or other) routes are registered and the app is listening."""
    for bot in BOTS.values():
        bot.register_bot_webhook()
# -- End Function register_all_bot_webhooks


def initialize_bots(bot_type: str, config: Dict[str, Any]) -> None:
    server_cfg = config["server"]

    BOTS.clear()
    for bot_key, bot_row in config.get("bots", {}).items():
        if not isinstance(bot_row, dict):
            raise ValueError(f"Bot {bot_key!r} must be a table.")
        bot_name = bot_row.get("name", bot_key)
        boot_logger = logging.getLogger(f"bootstrap.{bot_name}")

        try:
            validated_bot = bot_row.get("_validated_bot")
            validated_alert = bot_row.get("_validated_alert")
            if validated_bot is None or validated_alert is None:
                raise RuntimeError(
                    f"Bot {bot_key!r} missing validated config; run bootstrap() before initialize_bots()."
                )

            bot = create_bot_from_model(bot_type, validated_bot)
            bot.bot_key = bot_key
            bot.lookup_plugin = get_lookup_plugin()

            resolved_responders = RespondersList()
            refs = list(getattr(bot, "responder_refs", []))
            if bot.lookup_plugin is not None:
                resolved_responders = bot.lookup_plugin.resolve_responder_refs(
                    bot,
                    refs,
                    source_plugin="bot_config",
                )
            else:
                for raw in refs:
                    ref = (raw or "").strip()
                    if not ref:
                        continue
                    if ref.lower().startswith("person:"):
                        email = ref[7:].strip()
                        if email:
                            resolved_responders += ThaumPerson(email=email)
                        continue
                    if "@" in ref and not ref.lower().startswith("team:"):
                        resolved_responders += ThaumPerson(email=ref)
            bot.responders = resolved_responders

            plugin = get_plugin(validated_bot.alert_type, validated_alert)
            plugin.attach_bot(bot)
            bot.alert_plugin = plugin

            bind_thaum_handlers(bot)
            init_fn = getattr(bot, "complete_runtime_init", None)
            if callable(init_fn):
                init_fn(server_cfg)
            BOTS[bot_key] = bot
            boot_logger.log(LogLevel.VERBOSE, "Thaum bot '%s' initialized.", bot_name)
        except Exception as e:
            boot_logger.critical("Failed to bootstrap %s: %s", bot_name, e)
            raise
# -- End Function initialize_bots
