# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/leader_init.py
"""Registry and execution of one-shot leader-only tasks during process bootstrap."""
from __future__ import annotations

import json
import logging
import time
import traceback
from typing import Any, Callable, Dict, List, Tuple

from sqlalchemy.orm import Session

from gemstone_utils.db import get_session

from thaum.leader_init_status import (
    LEADER_INIT_ROW_ID,
    STATE_DONE,
    STATE_FAILED,
    STATE_IDLE,
    STATE_RUNNING,
    LeaderInitStatus,
    utcnow,
)
from thaum.types import LogLevel, ServerConfig
from log_setup import log_debug_blob

logger = logging.getLogger("thaum.leader_init")

_init_tasks: List[Tuple[str, Callable[[ServerConfig, Dict[str, Any]], None]]] = []


def register_init_task(
    name: str,
    fn: Callable[[ServerConfig, Dict[str, Any]], None],
) -> None:
    """Register a leader-only bootstrap task (plugins call via ``leader_init_tasks_register``)."""
    _init_tasks.append((name, fn))


def reset_for_tests() -> None:
    """Clear registered tasks (unit tests)."""
    _init_tasks.clear()


def _ensure_row(session: Session) -> LeaderInitStatus:
    row = session.get(LeaderInitStatus, LEADER_INIT_ROW_ID)
    if row is None:
        now = utcnow()
        row = LeaderInitStatus(
            id=LEADER_INIT_ROW_ID,
            barrier_ticket=0,
            state=STATE_IDLE,
            error_message=None,
            updated_at=now,
        )
        session.add(row)
    return row


def mark_leader_init_running(session: Session) -> None:
    """Leader: bump barrier ticket and set RUNNING (followers wait for done/failed on this ticket)."""
    row = _ensure_row(session)
    row.barrier_ticket = int(row.barrier_ticket) + 1
    row.state = STATE_RUNNING
    row.error_message = None
    row.updated_at = utcnow()


def mark_leader_init_done(session: Session) -> None:
    row = _ensure_row(session)
    row.state = STATE_DONE
    row.error_message = None
    row.updated_at = utcnow()


def mark_leader_init_failed(session: Session, message: str) -> None:
    row = _ensure_row(session)
    row.state = STATE_FAILED
    row.error_message = (message or "")[:1024]
    row.updated_at = utcnow()


def run_registered_init_tasks(server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    """Execute registered tasks in order; first failure stops and re-raises."""
    for i, (name, fn) in enumerate(_init_tasks):
        logger.log(
            LogLevel.VERBOSE,
            "Leader init task starting (%d/%d): %s",
            i + 1,
            len(_init_tasks),
            name,
        )
        try:
            fn(server_cfg, config)
        except Exception as e:
            logger.error("Leader init task %r failed: %s", name, e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(logger, f"leader init task traceback ({name})", traceback.format_exc(), LogLevel.SPAM)
            raise
        logger.log(LogLevel.VERBOSE, "Leader init task completed: %s", name)


def wait_for_leader_init_barrier(
    server_cfg: ServerConfig,
    *,
    poll_interval_seconds: float = 0.25,
) -> None:
    """
    Non-leader: block until the leader finishes init for this process start.

    Uses the first observed ``barrier_ticket`` as a baseline, then accepts ``done`` when the ticket
    increased (new cycle) or when we observed ``running`` before ``done`` at the same ticket
    (covers missing intermediate polls).
    """
    deadline = time.monotonic() + float(server_cfg.election.leader_init_wait_timeout_seconds)
    baseline: int | None = None
    saw_running = False
    failed_seen_at: float | None = None
    # region agent log
    def _dbg_wait(hypothesis_id: str, location: str, message: str, data: Dict[str, Any]) -> None:
        try:
            with open("/var/log/thaum/debug-131a48.log", "a", encoding="utf-8") as _f:
                _f.write(
                    json.dumps(
                        {
                            "sessionId": "131a48",
                            "timestamp": int(time.time() * 1000),
                            "runId": "leader-init-barrier",
                            "hypothesisId": hypothesis_id,
                            "location": location,
                            "message": message,
                            "data": data,
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
    # endregion agent log
    while True:
        if time.monotonic() > deadline:
            logger.error(
                "Timed out after %s s waiting for leader init barrier.",
                server_cfg.election.leader_init_wait_timeout_seconds,
            )
            raise RuntimeError("Leader init barrier wait timed out")

        with get_session() as session:
            row = session.get(LeaderInitStatus, LEADER_INIT_ROW_ID)
            if row is None:
                time.sleep(poll_interval_seconds)
                continue
            ticket = int(row.barrier_ticket)
            if baseline is None:
                baseline = ticket
                # region agent log
                _dbg_wait(
                    "H18",
                    "leader_init.py:wait_for_leader_init_barrier:baseline",
                    "captured baseline ticket/state",
                    {"baseline": baseline, "state": row.state},
                )
                # endregion agent log
            if row.state == STATE_RUNNING:
                saw_running = True
                failed_seen_at = None
            if row.state == STATE_FAILED:
                # region agent log
                _dbg_wait(
                    "H19",
                    "leader_init.py:wait_for_leader_init_barrier:failed_seen",
                    "observed failed barrier state",
                    {"ticket": ticket, "baseline": baseline, "saw_running": saw_running},
                )
                # endregion agent log
                if ticket > baseline or saw_running:
                    msg = row.error_message or "leader init failed"
                    logger.error("Leader init reported failure: %s", msg)
                    raise RuntimeError(msg)
                # If the first observed state is FAILED at baseline, give a brief grace
                # window for a concurrent fresh RUNNING ticket bump before failing.
                if failed_seen_at is None:
                    failed_seen_at = time.monotonic()
                elif (time.monotonic() - failed_seen_at) >= 2.0:
                    msg = row.error_message or "leader init failed"
                    logger.error("Leader init reported failure at baseline ticket: %s", msg)
                    raise RuntimeError(msg)
            if row.state == STATE_DONE:
                if ticket > baseline:
                    return
                if saw_running:
                    return
        time.sleep(poll_interval_seconds)
