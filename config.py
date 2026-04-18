# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# config.py
import logging
import tomllib
from typing import Any, Dict

from thaum.types import ServerConfig, LogConfig

logger = logging.getLogger("thaum.config")


def load_and_validate(path: str) -> Dict[str, Any]:
    """
    Load config.toml: parse TOML, validate ``[server]`` (including nested
    ``[server.database]``, ``[server.admin]``, ``[server.election]``) and ``[logging]``.

    Each ``[bots.<id>]`` may include ``alert_type`` and a nested ``[bots.<id>.alert]``
    table (exposed as key ``alert``); no normalization — bootstrap merges defaults later.
    """
    try:
        with open(path, "rb") as f:
            config_raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        logger.critical("Config file contains invalid TOML: %s", e)
        raise
    except Exception as e:
        logger.critical("Unknown error reading config: %s", e)
        raise

    server = config_raw.get("server")
    if not server:
        raise ValueError("config.toml is missing mandatory [server] section.")

    bots_raw = config_raw.get("bots", {})
    if not isinstance(bots_raw, dict):
        raise ValueError("[bots] must be a table.")
    normalized_bots: Dict[str, Any] = {}
    for bot_id, bot_cfg in bots_raw.items():
        if not isinstance(bot_cfg, dict):
            raise ValueError(f"Bot '{bot_id}' must be configured as a table/object.")
        normalized_bots[bot_id] = dict(bot_cfg)

    connections_raw = config_raw.get("connections", {})
    if not isinstance(connections_raw, dict):
        raise ValueError("[connections] must be a table.")

    config: Dict[str, Any] = {}
    config["raw"] = config_raw
    config["defaults"] = config_raw.get("defaults", {})
    config["lookup"] = config_raw.get("lookup", {})
    config["connections"] = connections_raw
    config["bots"] = normalized_bots
    try:
        config["server"] = ServerConfig(**server)
        config["log"] = LogConfig(**config_raw.get("logging", {}))
    except Exception as e:
        logger.critical("Configuration Validation Error: %s", e)
        raise

    return config
# -- End load_and_validate
