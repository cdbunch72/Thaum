# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/fatal.py
"""Irrecoverable startup path: log, best-effort stop parent (Gunicorn master), re-raise from caller."""

from __future__ import annotations

import logging
import os
import signal
from typing import Any

logger = logging.getLogger("thaum.fatal")


def fail_fast_fatal(reason: str, *, exc_info: Any = None) -> None:
    """
    Log a critical message, then best-effort send **SIGTERM** to the parent process (typically
    Gunicorn's master) so an orchestrator replaces the deployment.

    Call from an ``except`` block with ``exc_info=True`` to record the traceback. When
    ``getppid()`` is **1** or missing, the signal is skipped (foreground / tests).

    This does not replace normal exception propagation; callers should ``raise`` after calling.
    """
    try:
        logger.critical("Fatal setup: %s", reason, exc_info=exc_info)
        ppid = os.getppid()
        if ppid and ppid > 1:
            logger.critical(
                "Sending SIGTERM to parent pid=%s after fatal setup.",
                ppid,
            )
            os.kill(ppid, signal.SIGTERM)
    except Exception as e:
        logger.error("fail_fast_fatal follow-up failed: %s", e)


# -- End module thaum.fatal
