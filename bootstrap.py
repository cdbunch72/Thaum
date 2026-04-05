# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# bootstrap.py
from __future__ import annotations

import logging
from typing import Any, Dict

from pydantic import BaseModel

from alerts.webhook_bearer import set_thaum_state_dir
from bots.factory import validate_bot_config
from config import load_and_validate
from log_setup import apply_runtime_log_level_from_db, configure_logging, start_log_admin_state_poller
from lookup.factory import merged_lookup_plugin_config
from lookup.instance import initialize_lookup_plugin
from thaum.db_bootstrap import init_app_db, resolve_app_db_url
from plugin_loader import ensure_plugin_loaded, get_plugin_config_model
from thaum.database_crypto import apply_database_crypto, requires_database_vault_passphrase
from thaum.factory import initialize_bots
from thaum.maintenance_bootstrap import register_all_maintenance_tasks
from thaum.types import LogLevel, ServerConfig

logger = logging.getLogger("thaum.bootstrap")


def _merge_alert_defaults(defaults_root: Any, alert_type: str, instance: Any) -> Dict[str, Any]:
    da = (defaults_root or {}).get("alert") if isinstance(defaults_root, dict) else None
    da = da or {}
    raw_base = da.get(alert_type) if isinstance(da, dict) else None
    base = dict(raw_base) if isinstance(raw_base, dict) else {}
    inst = dict(instance) if isinstance(instance, dict) else {}
    merged: Dict[str, Any] = {**base, **inst}
    merged["plugin"] = alert_type
    return merged


def bootstrap(config_path: str) -> Dict[str, Any]:
    """
    Load config, logging, import plugins, validate all Pydantic configs, init DB,
    instantiate lookup + bots + alert plugins.
    """
    config = load_and_validate(config_path)
    server: ServerConfig = config["server"]

    configure_logging(config["log"], server)

    bot_type = server.bot_type
    lookup_type = server.lookup_plugin

    bot_rows = config.get("bots") or {}
    if not isinstance(bot_rows, dict):
        raise ValueError("[bots] must be a table.")

    alert_types: set[str] = {"null"}
    for row in bot_rows.values():
        if isinstance(row, dict):
            alert_types.add(str(row.get("alert_type", "null")))

    ensure_plugin_loaded("lookup", lookup_type)
    ensure_plugin_loaded("bots", bot_type)
    for at in alert_types:
        ensure_plugin_loaded("alerts", at)

    lookup_raw = config.get("lookup") if isinstance(config.get("lookup"), dict) else {}
    merged_lookup = merged_lookup_plugin_config(lookup_type, lookup_raw)
    lookup_mod = ensure_plugin_loaded("lookup", lookup_type)
    get_lm = getattr(lookup_mod, "get_config_model", None)
    if get_lm is None:
        raise ValueError(f"lookup.plugins.{lookup_type} must define get_config_model()")
    lookup_cfg_model: type[BaseModel] = get_lm()
    validated_lookup = lookup_cfg_model(**merged_lookup)

    defaults_root = config.get("defaults")
    for bot_key, bot_row in bot_rows.items():
        if not isinstance(bot_row, dict):
            raise ValueError(f"Bot {bot_key!r} must be a table.")
        validated_bot = validate_bot_config(bot_type, bot_key, bot_row, server)
        at = str(validated_bot.alert_type)
        instance_alert = bot_row.get("alert") if isinstance(bot_row.get("alert"), dict) else {}
        merged_a = _merge_alert_defaults(defaults_root, at, instance_alert)
        alert_cfg_model = get_plugin_config_model(at)
        validated_alert = alert_cfg_model(**merged_a)
        bot_row["_validated_bot"] = validated_bot
        bot_row["_validated_alert"] = validated_alert

    if requires_database_vault_passphrase(config):
        vp = server.database.database_vault_passphrase
        if vp is None or not str(vp).strip():
            raise ValueError(
                "server.database.database_vault_passphrase is required when a Webex bot omits "
                "hmac_secret (shared DB HMAC mode)."
            )

    set_thaum_state_dir(server.thaum_state_dir)

    db_url = resolve_app_db_url(server)
    init_app_db(db_url)
    apply_database_crypto(server)
    register_all_maintenance_tasks(server, config)

    apply_runtime_log_level_from_db()
    start_log_admin_state_poller(server)

    initialize_lookup_plugin(lookup_type, validated_lookup.model_dump(mode="python"))

    initialize_bots(bot_type, config)
    logger.log(LogLevel.VERBOSE, "Thaum bootstrap complete for config %s", config_path)
    return config
# -- End Function bootstrap
