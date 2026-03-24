# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import verboselogs
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from thaum.types import LogConfig, LogLevel, ServerConfig

NO_TIMESTAMP = False

# Path used for runtime log level overrides (defaults; overridden from ServerConfig).
DEFAULT_LOG_OVERRIDE_PATH = "/run/thaum/log_override"
LOG_OVERRIDE_PATH = DEFAULT_LOG_OVERRIDE_PATH

_configured_root_level: int = logging.INFO
_logger_wrappers_installed: bool = False

_original_logger_error = logging.Logger.error
_original_logger_exception = logging.Logger.exception
_override_watcher_started: bool = False
_override_polling_started: bool = False
_override_watcher_enabled: bool = False


def should_log_exception_trace() -> bool:
    """True when root log level enables SPAM (stack traces allowed)."""
    return logging.getLogger().isEnabledFor(verboselogs.SPAM)


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
    if hasattr(verboselogs, key):
        v = getattr(verboselogs, key)
        if isinstance(v, int):
            return int(v)
    return None


def _apply_log_override_file() -> None:
    """Apply / run/thaum/log_override or restore configured root level."""
    root = logging.getLogger()
    if not os.path.isfile(LOG_OVERRIDE_PATH):
        root.setLevel(_configured_root_level)
        return
    try:
        with open(LOG_OVERRIDE_PATH, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        level = parse_level_name(line)
        if level is None:
            root.setLevel(_configured_root_level)
        else:
            root.setLevel(level)
    except OSError:
        root.setLevel(_configured_root_level)


def _maybe_start_override_watcher() -> None:
    """
    Optional watchdog integration: when enabled, apply log overrides whenever
    the override file is created/modified/replaced.

    Controlled via `ServerConfig.log_override_watchdog`.
    """
    global _override_watcher_started
    if _override_watcher_started:
        return

    if not _override_watcher_enabled:
        return

    try:
        from watchdog.events import FileSystemEventHandler  # type: ignore
        from watchdog.observers import Observer  # type: ignore
    except Exception:
        # watchdog not installed (or broken). Polling can still be enabled via ServerConfig.
        return

    directory = os.path.dirname(LOG_OVERRIDE_PATH) or "."
    override_basename = os.path.basename(LOG_OVERRIDE_PATH)
    logger = logging.getLogger("log_setup")

    class _Handler(FileSystemEventHandler):
        def _matches(self, event) -> bool:
            src = getattr(event, "src_path", None) or ""
            return os.path.basename(src) == override_basename

        def on_created(self, event) -> None:
            if self._matches(event):
                _apply_log_override_file()

        def on_modified(self, event) -> None:
            if self._matches(event):
                _apply_log_override_file()

        def on_moved(self, event) -> None:
            if self._matches(event):
                _apply_log_override_file()

        def on_deleted(self, event) -> None:
            if self._matches(event):
                _apply_log_override_file()

    if not os.path.isdir(directory):
        # Don't crash workers if /run/thaum doesn't exist; reloader can be enabled via polling.
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            logger.warning("log_override watcher could not ensure directory %r exists", directory)
            return

    observer = Observer()
    observer.schedule(_Handler(), directory, recursive=False)
    observer.daemon = True
    observer.start()
    _override_watcher_started = True


def _maybe_start_override_polling(poll_seconds: float) -> None:
    """
    Dependency-free polling reloader.
    """
    global _override_polling_started
    if _override_polling_started:
        return
    if poll_seconds <= 0:
        return

    if poll_seconds <= 0:
        return

    try:
        last_mtime: Optional[float] = os.path.getmtime(LOG_OVERRIDE_PATH)
    except OSError:
        last_mtime = None

    def _loop() -> None:
        nonlocal last_mtime
        while True:
            try:
                exists = os.path.isfile(LOG_OVERRIDE_PATH)
                if not exists:
                    if last_mtime is not None:
                        last_mtime = None
                        _apply_log_override_file()
                else:
                    mtime = os.path.getmtime(LOG_OVERRIDE_PATH)
                    if last_mtime is None or mtime != last_mtime:
                        last_mtime = mtime
                        _apply_log_override_file()
            except Exception:
                # Never let the reload loop crash the worker.
                pass
            time.sleep(poll_seconds)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    _override_polling_started = True


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
        """Forces ISO 8601 output (e.g., 2023-10-25T14:30:15-05:00)."""
        global NO_TIMESTAMP
        if NO_TIMESTAMP:
            return ""
        dt = datetime.fromtimestamp(record.created, tz=self.tz)
        
        # 'seconds' truncates microseconds; 'auto' includes them
        spec = 'auto' if self.fractional_seconds else 'seconds'
        return dt.isoformat(timespec=spec)
# -- End ISO8601TimezoneFormatter

def log_debug_blob(logger: logging.Logger, blob_title: str, data: Any, level: int = logging.DEBUG):
    """
    Logs a multi-line blob wrapped in terminal-friendly delimiters (20 chars).
    Supports dynamic logging levels (DEBUG, SPAM, etc.).
    """
    if logger.isEnabledFor(level):
        delimiter = "-" * 20
        
        # Pretty print the JSON
        # If it's a dict, dump it, otherwise assume it's already a string
        formatted_json = json.dumps(data, indent=2) if isinstance(data, dict) else str(data)
        
        # Log using the requested level
        # We use .log() because it accepts the level integer as an argument
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

    # Apply runtime log override configuration from server settings.
    global LOG_OVERRIDE_PATH
    if server_config is not None:
        LOG_OVERRIDE_PATH = server_config.log_override_path or DEFAULT_LOG_OVERRIDE_PATH
        global _override_watcher_enabled
        _override_watcher_enabled = bool(server_config.log_override_watchdog)
        poll_seconds = float(server_config.log_override_poll_seconds)
    else:
        global _override_watcher_enabled
        _override_watcher_enabled = False
        poll_seconds = 1.0

    _apply_log_override_file()
    _maybe_start_override_watcher()
    _maybe_start_override_polling(poll_seconds)

    # Silence noisy web server frameworks (e.g., Werkzeug/Flask)
    # We want them to use our formatter, not their own
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers = [console_handler]
    werkzeug_logger.propagate = False

# -- End Function configure_logging
