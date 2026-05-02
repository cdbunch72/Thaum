# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# log_setup.py
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Tuple

from pythonjsonlogger.json import JsonFormatter
from zoneinfo import ZoneInfo


def _json_dumps_compact(log_data: Any, **kwargs: Any) -> str:
    """Match stdlib json.dumps one-line style (no spaces after ':' / ',')."""
    return json.dumps(
        log_data,
        default=kwargs.get("default"),
        cls=kwargs.get("cls"),
        ensure_ascii=kwargs.get("ensure_ascii", True),
        separators=(",", ":"),
    )

if TYPE_CHECKING:
    from thaum.types import LogConfig, ServerConfig

_configured_root_level: int = logging.INFO
_logger_wrappers_installed: bool = False
_early_logging_initialized: bool = False

_original_logger_error = logging.Logger.error
_original_logger_exception = logging.Logger.exception

# Last applied (log_level column, updated_at UTC timestamp) from admin_log_level_state.
_last_db_log_state: Optional[Tuple[Optional[str], float]] = None
_admin_state_poll_seconds: float = 0.0
_admin_state_poller_started: bool = False


def should_log_exception_trace() -> bool:
    """
    True when human-readable formatters should append traceback and stack dumps.
    Matches SPAM-enabled root logging; structured JSON sinks use record.exc_info
    independently of this gate.
    """
    from thaum.types import LogLevel

    return logging.getLogger().isEnabledFor(LogLevel.SPAM)


def parse_level_name(name: str) -> Optional[int]:
    """
    Resolve a level string to a numeric logging level, or None for invalid / DEFAULT.
    """
    from thaum.types import LogLevel

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


def start_log_admin_state_poller(server_config: Optional["ServerConfig"] = None) -> None:
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
    """
    Thin patch on Logger.error: at SPAM, default uncovered exc_info to True so bare
    .error() calls capture the active exception context. Never strips caller-supplied exc_info.
    Logger.exception stays stdlib (always records traceback on the LogRecord).
    """
    global _logger_wrappers_installed
    if _logger_wrappers_installed:
        return

    def _spam_default_exc_error(self: logging.Logger, msg: Any, *args: Any, **kwargs: Any) -> None:
        if should_log_exception_trace() and "exc_info" not in kwargs:
            kwargs["exc_info"] = True
        _original_logger_error(self, msg, *args, **kwargs)

    logging.Logger.error = _spam_default_exc_error  # type: ignore[method-assign]
    logging.Logger.exception = _original_logger_exception  # type: ignore[method-assign]
    _logger_wrappers_installed = True


class ISO8601TimezoneFormatter(logging.Formatter):
    def __init__(
        self,
        fmt: str,
        tz_string: str = "UTC",
        fractional_seconds: bool = False,
        *,
        no_timestamp: bool = False,
    ):
        super().__init__(fmt)
        self.tz_string = tz_string.strip()
        self.fractional_seconds = fractional_seconds
        self.no_timestamp = no_timestamp

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

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        if self.no_timestamp:
            return ""
        dt = datetime.fromtimestamp(record.created, tz=self.tz)
        spec = "auto" if self.fractional_seconds else "seconds"
        return dt.isoformat(timespec=spec)
# -- End ISO8601TimezoneFormatter


class SpamGatedTextFormatter(ISO8601TimezoneFormatter):
    """
    Human-readable (stdout/file) formatter: emits exc_text and stack_info only when
    should_log_exception_trace() (SPAM). Leaves record.exc_info intact for JSON sinks.
    """

    def format(self, record: logging.LogRecord) -> str:
        try:
            record.message = record.getMessage()
        except TypeError as te:
            raise TypeError(f"Unable to convert message: {record.msg!r}") from te
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        s = self.formatMessage(record)
        if should_log_exception_trace():
            if record.exc_info and not isinstance(record.exc_info, str):
                if record.exc_text is None:
                    record.exc_text = self.formatException(record.exc_info)
                if record.exc_text:
                    if s[-1:] != "\n":
                        s = s + "\n"
                    s = s + record.exc_text
            if record.stack_info:
                if s[-1:] != "\n":
                    s = s + "\n"
                s = s + self.formatStack(record.stack_info)
        return s


class SecureTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Timed rotation with best-effort chmod 0o600 on the active log file (Unix)."""

    def _chmod_active(self) -> None:
        try:
            if os.path.exists(self.baseFilename):
                os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass

    def _open(self) -> Any:
        stream = super()._open()
        self._chmod_active()
        return stream

    def doRollover(self) -> None:
        super().doRollover()
        self._chmod_active()


def _make_json_formatter() -> logging.Formatter:
    """One-line JSON records for machine-readable sinks (stderr / json_log file)."""
    return JsonFormatter(
        "%(levelname)s %(name)s %(message)s",
        rename_fields={
            "levelname": "level",
            "name": "logger",
            "timestamp": "ts",
            "exc_info": "exception",
        },
        timestamp=True,
        json_indent=None,
        json_ensure_ascii=True,
        json_serializer=_json_dumps_compact,
    )


def _register_custom_log_level_names() -> None:
    """So %(levelname)s shows SPAM / VERBOSE / NOTICE instead of Level N."""
    from thaum.types import LogLevel

    logging.addLevelName(int(LogLevel.SPAM), "SPAM")
    logging.addLevelName(int(LogLevel.VERBOSE), "VERBOSE")
    logging.addLevelName(int(LogLevel.NOTICE), "NOTICE")


def _env_truthy(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on", "truthy")


def _resolve_env_json_target(raw: str) -> Optional[str]:
    s = raw.strip()
    if not s:
        return None
    if _env_truthy(s):
        return "stderr"
    low = s.lower()
    if low.startswith("file:"):
        path = s[5:].strip()
        if path:
            return path
    return None


def get_env_log_level_override() -> Optional[int]:
    raw = os.environ.get("THAUM_LOG_LEVEL", "").strip()
    if not raw:
        return None
    parsed = parse_level_name(raw)
    if parsed is None:
        print(f"Thaum: ignoring invalid THAUM_LOG_LEVEL={raw!r}.", file=sys.stderr)
    return parsed


def _build_json_file_handler(path: str, backup_count: int) -> Optional[logging.Handler]:
    p = Path(path).expanduser()
    try:
        parent = p.resolve().parent
    except (OSError, RuntimeError):
        print(
            f"Thaum: cannot resolve json log file path {path!r}; JSON logging disabled.",
            file=sys.stderr,
        )
        return None
    if not parent.is_dir():
        print(
            f"Thaum: json log file directory does not exist ({parent}); JSON logging disabled.",
            file=sys.stderr,
        )
        return None
    try:
        file_handler = SecureTimedRotatingFileHandler(
            str(p),
            when="midnight",
            interval=1,
            backupCount=max(0, int(backup_count)),
            encoding="utf-8",
            delay=True,
        )
    except OSError as e:
        print(
            f"Thaum: cannot open json log file {path!r}: {e}; JSON logging disabled.",
            file=sys.stderr,
        )
        return None
    file_handler.setFormatter(_make_json_formatter())
    return file_handler


def _build_json_handler(target: str, backup_count: int) -> Optional[logging.Handler]:
    t = (target or "").strip().lower()
    if not t:
        return None
    if t == "stderr":
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(_make_json_formatter())
        return h
    return _build_json_file_handler(target, backup_count)


def init_early_logging_from_env() -> None:
    """
    Initialize minimal logging before config load.
    Uses THAUM_LOG_LEVEL and THAUM_JSON_LOG only.
    """
    global _early_logging_initialized
    if _early_logging_initialized:
        return
    _register_custom_log_level_names()
    root_logger = logging.getLogger()
    level = get_env_log_level_override()
    root_logger.setLevel(level if level is not None else logging.INFO)
    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SpamGatedTextFormatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                tz_string="UTC",
                fractional_seconds=False,
                no_timestamp=False,
            )
        )
        root_logger.addHandler(console_handler)
    env_target = _resolve_env_json_target(os.environ.get("THAUM_JSON_LOG", ""))
    if env_target is not None:
        json_handler = _build_json_handler(env_target, backup_count=5)
        if json_handler is not None:
            root_logger.addHandler(json_handler)
    _early_logging_initialized = True


def log_debug_blob(logger: logging.Logger, blob_title: str, data: Any, level: int = logging.DEBUG):
    if logger.isEnabledFor(level):
        delimiter = "-" * 20
        formatted_json = json.dumps(data, indent=2) if isinstance(data, dict) else str(data)
        logger.log(level, f"BEGIN {blob_title} {delimiter}")
        for line in formatted_json.splitlines():
            logger.log(level, line)
        logger.log(level, f"END {blob_title} {delimiter}")
# -- End Function log_debug_blob


def configure_logging(
    logging_config: "LogConfig",
    server_config: Optional["ServerConfig"] = None,
):
    """
    Sets up a global, single-line, timezone-aware logging system.
    Replaces existing root handlers; SPAM gates traceback/stack text on human sinks only.
    """
    global _configured_root_level

    tz_str = logging_config.timezone
    use_fractions = logging_config.fractional_seconds

    env_level_override = None if logging_config.override_env else get_env_log_level_override()
    _configured_root_level = (
        int(env_level_override)
        if env_level_override is not None
        else int(logging_config.level)
    )

    _register_custom_log_level_names()

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    console_formatter = SpamGatedTextFormatter(
        log_format,
        tz_string=tz_str,
        fractional_seconds=use_fractions,
        no_timestamp=logging_config.no_timestamp,
    )
    file_formatter = SpamGatedTextFormatter(
        log_format,
        tz_string=tz_str,
        fractional_seconds=use_fractions,
        no_timestamp=False,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(_configured_root_level)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    log_path = logging_config.file
    if log_path:
        p = Path(log_path).expanduser()
        try:
            parent = p.resolve().parent
        except (OSError, RuntimeError):
            print(
                f"Thaum: cannot resolve log file path {log_path!r}; file logging disabled.",
                file=sys.stderr,
            )
            parent = None
        if parent is not None:
            if not parent.is_dir():
                print(
                    f"Thaum: log file directory does not exist ({parent}); file logging disabled.",
                    file=sys.stderr,
                )
            else:
                try:
                    file_handler = SecureTimedRotatingFileHandler(
                        str(p),
                        when="midnight",
                        interval=1,
                        backupCount=max(0, int(logging_config.file_backup_count)),
                        encoding="utf-8",
                        delay=True,
                    )
                    file_handler.setFormatter(file_formatter)
                    root_logger.addHandler(file_handler)
                except OSError as e:
                    print(
                        f"Thaum: cannot open log file {log_path!r}: {e}; file logging disabled.",
                        file=sys.stderr,
                    )

    env_json_target = _resolve_env_json_target(os.environ.get("THAUM_JSON_LOG", ""))
    json_target: Optional[str] = None
    if (not logging_config.override_env) and env_json_target is not None:
        json_target = env_json_target
    else:
        json_target = logging_config.json_log
    if json_target:
        json_handler = _build_json_handler(
            json_target,
            backup_count=int(logging_config.file_backup_count),
        )
        if json_handler is not None:
            root_logger.addHandler(json_handler)

    _install_logger_wrappers()

    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers = list(root_logger.handlers)
    werkzeug_logger.propagate = False

# -- End Function configure_logging
