# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/leader_init.py
"""Registry and execution of one-shot leader-only tasks during process bootstrap."""
from __future__ import annotations

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
    for name, fn in _init_tasks:
        try:
            fn(server_cfg, config)
        except Exception as e:
            logger.error("Leader init task %r failed: %s", name, e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(logger, f"leader init task traceback ({name})", traceback.format_exc(), LogLevel.SPAM)
            raise


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
            if row.state == STATE_RUNNING:
                saw_running = True
            if row.state == STATE_FAILED and (ticket > baseline or saw_running):
                msg = row.error_message or "leader init failed"
                logger.error("Leader init reported failure: %s", msg)
                raise RuntimeError(msg)
            if row.state == STATE_DONE:
                if ticket > baseline:
                    return
                if saw_running:
                    return
        time.sleep(poll_interval_seconds)
