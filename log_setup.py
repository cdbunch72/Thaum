# Thaum Engine v1.0.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import logging
import verboselogs
import json
import sys
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
from thaum.types import LogConfig

NO_TIMESTAMP = False


class ISO8601TimezoneFormatter(logging.Formatter):
    def __init__(self, fmt, tz_string="UTC", fractional_seconds=False):
        super().__init__(fmt)
        self.tz_string = tz_string.strip()
        self.fractional_seconds = fractional_seconds
        
        # Determine Timezone
        if self.tz_string.lower() == "local":
            self.tz = None # Python uses system local time
        elif self.tz_string.lower() == "utc":
            self.tz = ZoneInfo("UTC")
        else:
            try:
                self.tz = ZoneInfo(self.tz_string)
            except Exception:
                # Fallback to UTC if admin provides an invalid timezone string
                self.tz = ZoneInfo("UTC")

    def formatTime(self, record, datefmt=None):
        """Forces ISO 8601 output (e.g., 2023-10-25T14:30:15-05:00)."""
        global NO_TIMESTAMP
        if NO_TIMESTAMP:
            return ''
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

def configure_logging(logging_config: LogConfig):
    """
    Sets up a global, single-line, timezone-aware logging system.
    This replaces existing handlers (like Flask's default noise).
    """

    tz_str = logging_config.timezone
    use_fractions = logging_config.fractional_seconds
    
    global NO_TIMESTAMP
    NO_TIMESTAMP = logging_config.no_timestamp

    # Configure the formatter
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = ISO8601TimezoneFormatter(log_format, tz_string=tz_str, fractional_seconds=use_fractions)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging_config.level)

    # Remove default handlers to prevent duplicated logs/stack traces
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Add our single-line console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    _original_error = logging.Logger.error

    def _smart_error(self, msg, *args, **kwargs):
        # If level is DEBUG or VERBOSE, force stack trace if not explicitly provided
        if self.isEnabledFor(verboselogs.SPAM) and 'exc_info' not in kwargs:
            kwargs['exc_info'] = True
        _original_error(self, msg, *args, **kwargs)

    logging.Logger.error = _smart_error

    # Silence noisy web server frameworks (e.g., Werkzeug/Flask)
    # We want them to use our formatter, not their own
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers = [console_handler]
    werkzeug_logger.propagate = False