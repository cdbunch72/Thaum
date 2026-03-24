# thaum/factory.py
# Copyright 2026 Clinton Bunch. All rights reserved.
# SPDX-License-Identifier: MPL-2.0

import logging
from bots.factory import create_bot
from bots.base import BaseChatBot
from typing import Dict,Any
from thaum.handlers import bind_thaum_handlers
from thaum.types import ThaumPerson, RespondersList
from plugin_loader import get_plugin
from lookup.instance import get_lookup_plugin

BOTS: Dict[str, BaseChatBot] = {}

def initialize_bots(bot_type: str, config: Dict[str, Any]) -> None:
    server_cfg = config["server"]  # ServerConfig (pydantic model)

    for bot_key, bot_config in config.get("bots", {}).items():
        bot_name = bot_config.get("name", bot_key)
        boot_logger = logging.getLogger(f"bootstrap.{bot_name}")
        
        try:
            bot_cfg = dict(bot_config)
            bot_cfg.setdefault("endpoint", f"{server_cfg.base_url}/webhooks/{bot_key}")
            bot = create_bot(bot_type, bot_cfg)
            bot.lookup_plugin = get_lookup_plugin()
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
            p_cfg = bot_config.get("alert", {})
            plugin = get_plugin(p_cfg.get("plugin", "NullPlugin"), p_cfg)
            plugin.attach_bot(bot)
            bot.alert_plugin = plugin
            
            # Auth
            if plugin.supports_status_webhooks:
                bot.auth_token = p_cfg.get("auth_token")
            
            bind_thaum_handlers(bot)
            BOTS[bot_key] = bot
            boot_logger.info(f"Thaum bot '{bot_name}' initialized.")
        except Exception as e:
            boot_logger.critical(f"Failed to bootstrap {bot_name}: {e}")
            raise
# -- End Function initialize_bots