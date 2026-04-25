# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
"""Session NDJSON debug log (container-friendly path; no outbound HTTP)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

# Prefer container path, but always fall back to local cwd so debug-mode evidence is captured.
AGENT_DEBUG_LOG_PATH = Path("/var/log/thaum/debug-978acd.log")
AGENT_DEBUG_FALLBACK_PATH = Path("debug-978acd.log")
DEBUG_SESSION_ID = "978acd"


def append_agent_debug_log(location: str, message: str, data: Dict[str, Any], hypothesis_id: str) -> None:
    # #region agent log
    payload = {
        "sessionId": DEBUG_SESSION_ID,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
        "hypothesisId": hypothesis_id,
    }

    for path in (AGENT_DEBUG_LOG_PATH, AGENT_DEBUG_FALLBACK_PATH):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, default=str) + "\n")
            return
        except Exception:
            continue
    # #endregion
