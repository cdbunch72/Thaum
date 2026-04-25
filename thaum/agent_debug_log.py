# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
"""Session NDJSON debug log (container-friendly path; no outbound HTTP)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

# Linux containers: mount or chmod this dir; no dependency on repo cwd or Windows workspace.
AGENT_DEBUG_LOG_PATH = Path("/var/log/thaum/debug-978acd.log")
DEBUG_SESSION_ID = "978acd"


def append_agent_debug_log(location: str, message: str, data: Dict[str, Any], hypothesis_id: str) -> None:
    # #region agent log
    try:
        AGENT_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": DEBUG_SESSION_ID,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
            "hypothesisId": hypothesis_id,
        }
        with open(AGENT_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
    # #endregion
