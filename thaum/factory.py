# thaum/factory.py
# Copyright 2026 <<Name>>. All rights reserved.

import logging
from bots.factory import create_bot
from bots.base import BaseChatBot
from typing import Dict,Any
from thaum.handlers import bind_thaum_handlers
from plugin_loader import get_plugin
from config import resolve_config_key

BOTS: Dict[str, BaseChatBot] = {}

def initialize_bots(bot_type: str, config: Dict[str, Any]) -> None:
    for bot_key, bot_config in config.get("bots", {}).items():
        bot_name = bot_config.get("name", bot_key)
        boot_logger = logging.getLogger(f"bootstrap.{bot_name}")
        
        try:
            token = resolve_config_key(bot_config, "token", boot_logger, required=True)
            secret = resolve_config_key(bot_config, "secret", boot_logger, required=False, default="RANDOM", allow_empty=True)
            endpoint = bot_config.get("endpoint") or f"{config['server']['base_url']}/webhooks/{bot_key}"
            
            bot = create_bot(bot_type, bot_name, endpoint, token=token, secret=secret)
            
            # Feature Flags
            bot.emergency_enabled = bot_config.get("emergency_enabled", True)
            bot.incident_room_only = bot_config.get("incident_room_only", False)
            bot.responders = bot_config.get("responders", [])
            bot.room_title_template = bot_config.get("room_title_template", "Incident: {summary}")
            
            # Plugin Loading
            p_cfg = bot_config.get("alert", {})
            plugin = get_plugin(p_cfg.get("plugin", "NullPlugin"), p_cfg)
            plugin.attach_bot(bot)
            bot.alert_plugin = plugin
            
            # Auth
            if plugin.supports_status_webhooks:
                bot.auth_token = resolve_config_key(p_cfg, "auth_token", boot_logger, required=True, allow_empty=True)
            
            bind_thaum_handlers(bot)
            BOTS[bot_key] = bot
            boot_logger.info(f"Thaum bot '{bot_name}' initialized.")
        except Exception as e:
            boot_logger.critical(f"Failed to bootstrap {bot_name}: {e}")
            raise
# -- End Function initialize_bots