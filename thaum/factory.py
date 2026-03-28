# thaum/factory.py
# Copyright 2026 Clinton Bunch. All rights reserved.
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import logging
from typing import Any, Dict

from bots.base import BaseChatBot
from bots.factory import create_bot_from_model
from lookup.instance import get_lookup_plugin
from plugin_loader import get_plugin
from thaum.handlers import bind_thaum_handlers
from thaum.types import LogLevel, ThaumPerson, RespondersList

BOTS: Dict[str, BaseChatBot] = {}


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
            for ref in getattr(bot, "responder_refs", []):
                if ref.startswith("person:"):
                    email = ref[7:].strip()
                    if email:
                        resolved_responders += ThaumPerson(email=email)
                    continue

                if ref.startswith("team:"):
                    team_name = ref[5:].strip()
                    if not team_name:
                        continue
                    team = bot.lookup_plugin.get_team_by_name(bot, team_name)
                    if team is not None:
                        resolved_responders += team
                    else:
                        boot_logger.warning(
                            "Responder team '%s' was not found in lookup cache.", team_name
                        )
                    continue

                if "@" in ref:
                    email = ref.strip()
                    if email:
                        resolved_responders += ThaumPerson(email=email)
                    continue

                team = bot.lookup_plugin.get_team_by_name(bot, ref)
                if team is not None:
                    resolved_responders += team
                else:
                    boot_logger.warning(
                        "Responder reference '%s' did not resolve as person or team.", ref
                    )
            bot.responders = resolved_responders

            plugin = get_plugin(validated_bot.alert_type, validated_alert)
            plugin.attach_bot(bot)
            bot.alert_plugin = plugin

            bind_thaum_handlers(bot)
            BOTS[bot_key] = bot
            boot_logger.log(LogLevel.VERBOSE, "Thaum bot '%s' initialized.", bot_name)
        except Exception as e:
            boot_logger.critical("Failed to bootstrap %s: %s", bot_name, e)
            raise
# -- End Function initialize_bots
