# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# bootstrap.py
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from pydantic import BaseModel
from gemstone_utils import election

from bots.factory import validate_bot_config
from config import load_and_validate
from connections.merge import merge_connection_profile
from log_setup import apply_runtime_log_level_from_db, configure_logging, start_log_admin_state_poller
from lookup.factory import merge_lookup_connection_profile, merged_lookup_plugin_config
from lookup.instance import initialize_lookup_plugin
from thaum.db_bootstrap import init_app_db, resolve_app_db_url
from plugin_loader import ensure_plugin_loaded, get_plugin_config_model
from thaum.database_crypto import apply_database_crypto, requires_database_vault_passphrase
from thaum.factory import initialize_bots
from thaum.leader_bootstrap import run_leader_bootstrap_phase
from thaum.maintenance_bootstrap import register_all_maintenance_tasks
from thaum.types import DEFAULT_LOG_FILE_PATH, LogLevel, LogConfig, ServerConfig

logger = logging.getLogger("thaum.bootstrap")


def _log_config_with_env_defaults(log_cfg: LogConfig) -> LogConfig:
    """If ``THAUM_LOG_TO_VAR_LOG`` is set, enable default file logging when TOML did not set ``file``."""
    v = os.environ.get("THAUM_LOG_TO_VAR_LOG", "").strip().lower()
    if not v or v not in ("1", "true", "yes", "on"):
        return log_cfg
    if log_cfg.file is not None:
        return log_cfg
    return log_cfg.model_copy(update={"file": DEFAULT_LOG_FILE_PATH})


def _merge_alert_defaults(defaults_root: Any, alert_type: str, instance: Any) -> Dict[str, Any]:
    da = (defaults_root or {}).get("alert") if isinstance(defaults_root, dict) else None
    da = da or {}
    raw_base = da.get(alert_type) if isinstance(da, dict) else None
    base = dict(raw_base) if isinstance(raw_base, dict) else {}
    inst = dict(instance) if isinstance(instance, dict) else {}
    merged: Dict[str, Any] = {**base, **inst}
    merged["plugin"] = alert_type
    return merged


def validate_config_after_load(config: Dict[str, Any]) -> BaseModel:
    """
    Import plugins and validate lookup, bot, and alert plugin Pydantic models.

    Mutates each ``[bots.<id>]`` row with ``_validated_bot`` and ``_validated_alert``.
    Returns the validated lookup plugin config instance.
    """
    server: ServerConfig = config["server"]

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
    merged_lookup = merge_lookup_connection_profile(config, merged_lookup)
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
        merged_a = merge_connection_profile(config, merged_a)
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

    return validated_lookup


def bootstrap(config_path: str) -> Dict[str, Any]:
    """
    Load config, logging, import plugins, validate all Pydantic configs, init DB,
    instantiate lookup, run election leader init (barrier), then bots + alert plugins.

    Sets ``config["_thaum_leader_candidate_id"]`` for :func:`web.create_app` to pass to the leader loop.
    """
    config = load_and_validate(config_path)
    server: ServerConfig = config["server"]

    configure_logging(_log_config_with_env_defaults(config["log"]), server)
    logger.error(
        "[debug-131a48][H6] bootstrap entered config_path=%s module=%s",
        config_path,
        __file__,
    )

    validated_lookup = validate_config_after_load(config)
    lookup_type = server.lookup_plugin
    bot_type = server.bot_type

    db_url = resolve_app_db_url(server)
    init_app_db(db_url)
    apply_database_crypto(server)
    register_all_maintenance_tasks(server, config)

    apply_runtime_log_level_from_db()
    start_log_admin_state_poller(server)

    logger.log(LogLevel.VERBOSE, "Bootstrap: initializing lookup plugin %r", lookup_type)
    initialize_lookup_plugin(lookup_type, validated_lookup.model_dump(mode="python"))

    logger.log(
        LogLevel.VERBOSE,
        "Bootstrap: leader election bootstrap phase (namespace=%r)",
        server.election.namespace,
    )
    leader_candidate_id = run_leader_bootstrap_phase(server, config)
    config["_thaum_leader_candidate_id"] = leader_candidate_id
    logger.log(
        LogLevel.VERBOSE,
        "Bootstrap: leader bootstrap finished; worker_candidate_id=%s",
        leader_candidate_id,
    )

    logger.log(LogLevel.VERBOSE, "Bootstrap: initializing bots (bot_type=%r)", bot_type)
    initialize_bots(bot_type, config)
    if election.is_leader(leader_candidate_id, server.election.namespace):
        from thaum.leader_service import run_startup_leader_tasks

        logger.log(LogLevel.VERBOSE, "Bootstrap: leader maintenance tasks (run_on_startup)")
        run_startup_leader_tasks(server, config)
    logger.log(LogLevel.VERBOSE, "Thaum bootstrap complete for config %s", config_path)
    return config
# -- End Function bootstrap
