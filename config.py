# Thaum v1.0.0
# Copyright 2026 Clinton Bunch. All rights reserved.
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import os
import logging
import tomllib
from typing import Dict, Any, Optional
from thaum.types import ServerConfig,LogConfig
from lookup.instance import initialize_lookup_plugin
from lookup.db_bootstrap import init_lookup_db, resolve_lookup_db_url
from alerts.webhook_bearer import set_thaum_state_dir

logger = logging.getLogger("thaum.config")

def _normalize_alert_block(alert_cfg: Any) -> Dict[str, Any]:
    """
    Normalize alert plugin config from either style:
      1) {"plugin": "jira", ...plugin fields...}
      2) {"jira": {...plugin fields...}}
    Returns {"plugin": "<name>", ...plugin fields...}
    """
    if not isinstance(alert_cfg, dict) or not alert_cfg:
        return {}

    if "plugin" in alert_cfg:
        return dict(alert_cfg)

    plugin_keys = [k for k, v in alert_cfg.items() if isinstance(v, dict)]
    if len(plugin_keys) != 1:
        raise ValueError(
            "Alert config must define exactly one plugin table when using nested "
            "[bots.<id>.alert.<plugin>] syntax."
        )

    plugin_name = plugin_keys[0]
    merged = dict(alert_cfg[plugin_name])
    merged["plugin"] = plugin_name
    return merged


def normalize_alert_block(alert_cfg: Any) -> Dict[str, Any]:
    """Public wrapper: flatten nested `[bots.*.alert.<plugin>]` TOML into a single dict with `plugin` key."""
    return _normalize_alert_block(alert_cfg)


def load_and_validate(path: str) -> Dict[str, Any]:
    """Loads the file format-agnostically."""
    try:
        with open(path, "rb") as f:
            config_raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        logger.critical(f"Config file contains invalid TOML: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unknown error reading config: {e}")
        raise

    # Validate mandatory [server] section
    server = config_raw.get("server")
    if not server:
        raise ValueError("config.toml is missing mandatory [server] section.")
    defaults_cfg = config_raw.get("defaults", {})

    normalized_bots: Dict[str, Any] = {}
    for bot_id, bot_cfg in config_raw.get("bots", {}).items():
        if not isinstance(bot_cfg, dict):
            raise ValueError(f"Bot '{bot_id}' must be configured as a table/object.")
        nb = dict(bot_cfg)
        if nb.get("alert"):
            nb["alert"] = _normalize_alert_block(nb["alert"])
        else:
            nb["alert"] = {}
        normalized_bots[bot_id] = nb

    config ={}
    config['raw']=config_raw
    config['defaults']=defaults_cfg
    config['lookup']=config_raw.get("lookup", {})
    config['bots']=normalized_bots
    try:
        config['server']=ServerConfig(**server)
        config['log']=LogConfig(**config_raw.get('logging',{}))
    except (Exception) as e:
        logger.critical(f"Configuration Validation Error: {e}")
        raise

    return config
#-- End load_and_validate


def initialize_runtime_plugins(config: Dict[str, Any]) -> None:
    """
    Initialize singleton runtime plugins from validated configuration.
    Intended to be called once during server bootstrap.
    """
    server_cfg: ServerConfig = config["server"]
    set_thaum_state_dir(server_cfg.thaum_state_dir)
    lookup_cfg = config.get("lookup", {})
    init_lookup_db(resolve_lookup_db_url(server_cfg, lookup_cfg))
    initialize_lookup_plugin(server_cfg.lookup_plugin, lookup_cfg)


def resolve_config_key(config_block, key_name, logger, required=True, default=None, allow_empty=False):
    """
    SysAdmin-grade config resolver. 
    Handles missing keys, empty strings (foot-aiming), and secure secret resolution.
    """
    val = config_block.get(key_name)

    # 1. Handle Missing Key
    if val is None:
        if required:
            raise ValueError(f"CRITICAL: '{key_name}' is required. See Thaum Documentation.")
        return default

    # 2. Handle Explicit "I want to disable this" (Empty String)
    if val == "":
        if not allow_empty:
            raise ValueError(f"CONFIGURATION ERROR: '{key_name}' cannot be empty.")
        else:
            logger.warning(f"SECURITY: '{key_name}' explicitly set to empty/disabled. Proceeding.")
            return None

    # 3. Resolve actual value (Literal, Env, Secret, or File)
    return _resolve_source(val, key_name, logger)

# -- End Function resolve_config_key

def _resolve_source(value, field_name, logger):
    """Internal helper to identify if the config value is a pointer or a literal."""
    
    # Handle non-string values (booleans, ints)
    if not isinstance(value, str):
        return value

    # Env Variable Source
    if value.startswith("env:"):
        env_var = value[4:]
        logger.verbose(f"[{field_name}] resolving from env: {env_var}")
        resolved = os.environ.get(env_var)
        if resolved is None:
            raise ValueError(f"Environment variable '{env_var}' not set.")
        return resolved.strip()

    # Orchestrator Secret Source (Systemd / K8s / Docker)
    elif value.startswith("secret:"):
        secret_name = value[7:]
        # Check systemd credentials first, then standard K8s/Docker path
        paths = [
            os.path.join(os.environ.get("CREDENTIALS_DIRECTORY", ""), secret_name),
            f"/run/secrets/{secret_name}"
        ]
        
        for path in paths:
            if os.path.isfile(path):
                logger.verbose(f"[{field_name}] resolving from secret: {path}")
                with open(path, "r") as f:
                    return f.read().strip()
        
        raise ValueError(f"Secret '{secret_name}' not found. Checked: {paths}")

    # Explicit File Source
    elif value.startswith("file:"):
        file_path = value[5:]
        logger.verbose(f"[{field_name}] resolving from file: {file_path}")
        if not os.path.isfile(file_path):
            raise ValueError(f"File not found at '{file_path}'.")
        with open(file_path, "r") as f:
            return f.read().strip()

    # Literal Value
    else:
        logger.verbose(f"[{field_name}] resolving from literal.")
        return value

# -- End Function _resolve_source