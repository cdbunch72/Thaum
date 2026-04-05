# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from zoneinfo import ZoneInfo

from thaum.types import LogConfig, LogLevel, ServerConfig

NO_TIMESTAMP = False

_configured_root_level: int = logging.INFO
_logger_wrappers_installed: bool = False

_original_logger_error = logging.Logger.error
_original_logger_exception = logging.Logger.exception

# Last applied (log_level column, updated_at UTC timestamp) from admin_log_level_state.
_last_db_log_state: Optional[Tuple[Optional[str], float]] = None
_admin_state_poll_seconds: float = 0.0
_admin_state_poller_started: bool = False


def should_log_exception_trace() -> bool:
    """True when root log level enables SPAM (stack traces allowed)."""
    return logging.getLogger().isEnabledFor(LogLevel.SPAM)


def parse_level_name(name: str) -> Optional[int]:
    """
    Resolve a level string to a numeric logging level, or None for invalid / DEFAULT.
    """
    key = name.strip().upper()
    if not key or key == "DEFAULT":
        return None
    if key in LogLevel.__members__:
        return int(LogLevel[key])
    if hasattr(logging, key) and isinstance(getattr(logging, key), int):
        return int(getattr(logging, key))
    return None


def set_runtime_root_log_level(level: Optional[int]) -> None:
    """Apply runtime override (None = restore configured [logging] level)."""
    root = logging.getLogger()
    if level is None:
        root.setLevel(_configured_root_level)
    else:
        root.setLevel(level)


def _utc_ts(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


def mark_db_log_state_applied(log_level: Optional[str], updated_at: datetime) -> None:
    """Call after a successful admin POST so the DB poller skips redundant applies."""
    global _last_db_log_state
    _last_db_log_state = (log_level, _utc_ts(updated_at))


def apply_runtime_log_level_from_db() -> None:
    """
    Read singleton admin_log_level_state and align root logger.
    Safe to call before row exists; no-op if unchanged vs last apply.
    """
    global _last_db_log_state

    from gemstone_utils.db import get_session

    from thaum.admin_models import ADMIN_LOG_LEVEL_STATE_ID, AdminLogLevelState

    try:
        with get_session() as session:
            row = session.get(AdminLogLevelState, ADMIN_LOG_LEVEL_STATE_ID)
    except Exception:
        return

    if row is None:
        sig: Tuple[Optional[str], float] = (None, -1.0)
        if sig == _last_db_log_state:
            return
        _last_db_log_state = sig
        set_runtime_root_log_level(None)
        return

    key: Tuple[Optional[str], float] = (row.log_level, _utc_ts(row.updated_at))
    if key == _last_db_log_state:
        return
    _last_db_log_state = key

    if row.log_level is None or not str(row.log_level).strip():
        set_runtime_root_log_level(None)
        return
    parsed = parse_level_name(str(row.log_level))
    if parsed is None:
        set_runtime_root_log_level(None)
    else:
        set_runtime_root_log_level(parsed)


def start_log_admin_state_poller(server_config: Optional[ServerConfig] = None) -> None:
    """Background poll of admin_log_level_state (call after init_db)."""
    global _admin_state_poller_started, _admin_state_poll_seconds

    if _admin_state_poller_started:
        return
    if server_config is None:
        return

    _admin_state_poll_seconds = float(server_config.admin.log_state_poll_seconds)
    if _admin_state_poll_seconds <= 0:
        return

    _admin_state_poller_started = True

    def _loop() -> None:
        while True:
            time.sleep(_admin_state_poll_seconds)
            try:
                apply_runtime_log_level_from_db()
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def _install_logger_wrappers() -> None:
    global _logger_wrappers_installed
    if _logger_wrappers_installed:
        return

    def _smart_error(self: logging.Logger, msg: Any, *args: Any, **kwargs: Any) -> None:
        # Stack traces only when root enables SPAM; strip exc_info otherwise.
        if should_log_exception_trace():
            if "exc_info" not in kwargs:
                kwargs["exc_info"] = True
        else:
            kwargs.pop("exc_info", None)
        _original_logger_error(self, msg, *args, **kwargs)

    def _smart_exception(self: logging.Logger, msg: Any, *args: Any, **kwargs: Any) -> None:
        if should_log_exception_trace():
            kwargs.setdefault("exc_info", True)
            _original_logger_exception(self, msg, *args, **kwargs)
        else:
            exc = sys.exc_info()[1]
            suffix = f" ({type(exc).__name__}: {exc})" if exc else ""
            kwargs.pop("exc_info", None)
            _original_logger_error(self, str(msg) + suffix, *args, **kwargs)

    logging.Logger.error = _smart_error  # type: ignore[method-assign]
    logging.Logger.exception = _smart_exception  # type: ignore[method-assign]
    _logger_wrappers_installed = True


class ISO8601TimezoneFormatter(logging.Formatter):
    def __init__(self, fmt, tz_string="UTC", fractional_seconds=False):
        super().__init__(fmt)
        self.tz_string = tz_string.strip()
        self.fractional_seconds = fractional_seconds
        
        # Determine Timezone
        if self.tz_string.lower() == "local":
            self.tz = None
        elif self.tz_string.lower() == "utc":
            self.tz = ZoneInfo("UTC")
        else:
            try:
                self.tz = ZoneInfo(self.tz_string)
            except Exception:
                self.tz = ZoneInfo("UTC")

    def formatTime(self, record, datefmt=None):
        global NO_TIMESTAMP
        if NO_TIMESTAMP:
            return ""
        dt = datetime.fromtimestamp(record.created, tz=self.tz)
        spec = "auto" if self.fractional_seconds else "seconds"
        return dt.isoformat(timespec=spec)
# -- End ISO8601TimezoneFormatter


def _register_custom_log_level_names() -> None:
    """So %(levelname)s shows SPAM / VERBOSE / NOTICE instead of Level N."""
    logging.addLevelName(int(LogLevel.SPAM), "SPAM")
    logging.addLevelName(int(LogLevel.VERBOSE), "VERBOSE")
    logging.addLevelName(int(LogLevel.NOTICE), "NOTICE")


def log_debug_blob(logger: logging.Logger, blob_title: str, data: Any, level: int = logging.DEBUG):
    if logger.isEnabledFor(level):
        delimiter = "-" * 20
        formatted_json = json.dumps(data, indent=2) if isinstance(data, dict) else str(data)
        logger.log(level, f"BEGIN {blob_title} {delimiter}")
        for line in formatted_json.splitlines():
            logger.log(level, line)
        logger.log(level, f"END {blob_title} {delimiter}")
# -- End Function log_debug_blob

def configure_logging(logging_config: LogConfig, server_config: Optional[ServerConfig] = None):
    """
    Sets up a global, single-line, timezone-aware logging system.
    Replaces existing root handlers and installs SPAM-gated exception traces.
    """
    global NO_TIMESTAMP, _configured_root_level

    tz_str = logging_config.timezone
    use_fractions = logging_config.fractional_seconds

    NO_TIMESTAMP = logging_config.no_timestamp
    _configured_root_level = int(logging_config.level)

    _register_custom_log_level_names()

    # Configure the formatter
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = ISO8601TimezoneFormatter(
        log_format, tz_string=tz_str, fractional_seconds=use_fractions
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(_configured_root_level)

    # Remove default handlers to prevent duplicated logs/stack traces
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Add our single-line console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    _install_logger_wrappers()

    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers = [console_handler]
    werkzeug_logger.propagate = False

# -- End Function configure_logging

