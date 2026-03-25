# thaum/factory.py
# Copyright 2026 Clinton Bunch. All rights reserved.
# SPDX-License-Identifier: MPL-2.0

import logging
from bots.factory import create_bot
from bots.base import BaseChatBot
from typing import Any, Dict
from thaum.handlers import bind_thaum_handlers
from thaum.types import ThaumPerson, RespondersList
from plugin_loader import get_plugin, get_plugin_config_model
from lookup.instance import get_lookup_plugin
from config import normalize_alert_block

BOTS: Dict[str, BaseChatBot] = {}


def register_all_bot_webhooks() -> None:
    """Call after Flask (or other) routes are registered and the app is listening."""
    for bot in BOTS.values():
        bot.register_bot_webhook()
# -- End Function register_all_bot_webhooks


def initialize_bots(bot_type: str, config: Dict[str, Any]) -> None:
    server_cfg = config["server"]  # ServerConfig (pydantic model)

    for bot_key, bot_config in config.get("bots", {}).items():
        bot_name = bot_config.get("name", bot_key)
        boot_logger = logging.getLogger(f"bootstrap.{bot_name}")
        
        try:
            bot_cfg = dict(bot_config)
            bot_cfg.setdefault("endpoint", f"{server_cfg.base_url}/bot/{bot_key}")
            bot = create_bot(bot_type, bot_cfg)
            bot.bot_key = bot_key
            bot.lookup_plugin = get_lookup_plugin()

            raw_alert_cfg = normalize_alert_block(bot_config.get("alert", {}))
            plugin_name = raw_alert_cfg.get("plugin", "NullPlugin")
            defaults_root = config.get("defaults") or {}
            defaults_alert = defaults_root.get("alert") or {}
            default_alert_cfg = defaults_alert.get(plugin_name, {}) or {}
            if default_alert_cfg and not isinstance(default_alert_cfg, dict):
                raise ValueError(f"[defaults.alert.{plugin_name}] must be a table/object.")
            merged_alert_dict: Dict[str, Any] = {**default_alert_cfg, **raw_alert_cfg}
            config_model = get_plugin_config_model(plugin_name)
            p_cfg = config_model(**merged_alert_dict)
            resolved_responders = RespondersList()
            for ref in getattr(bot, "responder_refs", []):
                if ref.startswith("person:"):
                    email = ref[7:].strip()
                    if email:
                        resolved_responders += ThaumPerson(email=email, display_name=email, source_plugin="config")
                    continue

                if ref.startswith("team:"):
                    team_name = ref[5:].strip()
                    if not team_name:
                        continue
                    team = bot.lookup_plugin.get_team_by_name(bot, team_name)
                    if team is not None:
                        resolved_responders += team
                    else:
                        boot_logger.warning(f"Responder team '{team_name}' was not found in lookup cache.")
                    continue

                if "@" in ref:
                    email = ref.strip()
                    if email:
                        resolved_responders += ThaumPerson(email=email, display_name=email, source_plugin="config")
                    continue

                team = bot.lookup_plugin.get_team_by_name(bot, ref)
                if team is not None:
                    resolved_responders += team
                else:
                    boot_logger.warning(f"Responder reference '{ref}' did not resolve as person or team.")
            bot.responders = resolved_responders

            # Plugin Loading
            plugin = get_plugin(plugin_name, p_cfg)
            plugin.attach_bot(bot)
            bot.alert_plugin = plugin

            bind_thaum_handlers(bot)
            BOTS[bot_key] = bot
            boot_logger.info(f"Thaum bot '{bot_name}' initialized.")
        except Exception as e:
            boot_logger.critical(f"Failed to bootstrap {bot_name}: {e}")
            raise
# -- End Function initialize_bots