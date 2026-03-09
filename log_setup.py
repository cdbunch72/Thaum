# Thaum Engine v1.0.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import logging
import verboselogs
import json
import sys
from datetime import datetime

# Python 3.9+ standard
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for older environments
    from backports.zoneinfo import ZoneInfo 

# Global toggle: True will print the full stack trace on errors
SHOW_STACKTRACE = False

class ComponentFilter(logging.Filter):
    def __init__(self, noisy_components, root_level):
        super().__init__()
        self.noisy_components = noisy_components
        self.root_level = root_level

    def filter(self, record):
        # If the root level is DEBUG, let everything through
        if self.root_level <= logging.DEBUG:
            return True
        
        # If the log is tagged as noisy, suppress it
        if record.name in self.noisy_components:
            return False
            
        return True
# -- End ComponentFilter

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
        dt = datetime.fromtimestamp(record.created, tz=self.tz)
        
        # 'seconds' truncates microseconds; 'auto' includes them
        spec = 'auto' if self.fractional_seconds else 'seconds'
        return dt.isoformat(timespec=spec)
# -- End ISO8601TimezoneFormatter


def log_debug_blob(logger, blob_title, data):
    """
    Logs a multi-line blob wrapped in delimiters for easy visual scanning.
    """
    # Only log this if the logger's level is DEBUG
    if logger.isEnabledFor(logging.DEBUG):
        delimiter = "-" * 50
        # Pretty print the JSON
        formatted_json = json.dumps(data, indent=2)
        
        # We manually build the lines so we can ensure the timestamp 
        # is prepended to EVERY line in the block (Grep-friendly)
        logger.debug(f"BEGIN {blob_title} {delimiter}")
        for line in formatted_json.splitlines():
            logger.debug(line)
        logger.debug(f"END {blob_title} {delimiter}")

def configure_logging(logging_config):
    """
    Sets up a global, single-line, timezone-aware logging system.
    This replaces existing handlers (like Flask's default noise).
    """
    verboselogs.install()
    level_str = logging_config.get("level", "INFO").upper()
    tz_str = logging_config.get("timezone", "UTC")
    use_fractions = logging_config.get("fractional_seconds", False)

    # Configure the formatter
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = ISO8601TimezoneFormatter(log_format, tz_string=tz_str, fractional_seconds=use_fractions)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level_str, logging.INFO))

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