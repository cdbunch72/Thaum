# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# bots/factory.py
from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, ValidationError

from bots.base import BaseChatBot
from plugin_loader import ensure_plugin_loaded
from thaum.types import ServerConfig

logger = logging.getLogger("bots.factory")

_RUNTIME_KEYS = frozenset({"alert", "_validated_bot", "_validated_alert"})


def _bot_endpoint(server_cfg: ServerConfig, bot_key: str) -> str:
    prefix = (server_cfg.bot_url_prefix or "/bot").rstrip("/")
    return f"{server_cfg.base_url}{prefix}/{bot_key}"


def validate_bot_config(
    bot_type: str,
    bot_key: str,
    bot_row: dict[str, Any],
    server_cfg: ServerConfig,
) -> BaseModel:
    """
    Load the bot plugin module and validate ``bot_row`` with its Pydantic model.

    Strips ``alert`` (per-bot alert instance table) and runtime-only keys; sets ``endpoint``.
    """
    bot_name = bot_row.get("name", bot_key)
    try:
        module = ensure_plugin_loaded("bots", bot_type)
        config_model = module.get_config_model()
        clean = {k: v for k, v in bot_row.items() if k not in _RUNTIME_KEYS}
        clean.setdefault("endpoint", _bot_endpoint(server_cfg, bot_key))
        return config_model(**clean)
    except Exception as e:
        logger.critical("Invalid configuration for bot '%s': %s", bot_name, e)
        if isinstance(e, ValidationError):
            raise
        raise


def create_bot_from_model(bot_type: str, cfg: BaseModel) -> BaseChatBot:
    """Instantiate a bot from an already-validated config model."""
    try:
        module = ensure_plugin_loaded("bots", bot_type)
        factory_func = getattr(module, "create_instance_bot")
        return factory_func(cfg)
    except ImportError as e:
        bots_dir = os.path.join(os.path.dirname(__file__), "plugins")
        ignore_files = {"__init__.py"}
        available = [
            f.replace(".py", "")
            for f in os.listdir(bots_dir)
            if f.endswith(".py") and f not in ignore_files
        ]
        logger.critical("Failed to load bot driver '%s': %s", bot_type, e)
        raise ValueError(f"Bot type '{bot_type}' not found. Available: {available}") from e
    except AttributeError as e:
        logger.critical("Bot module '%s' missing required entry point: %s", bot_type, e)
        raise
