# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/leader_service.py
from __future__ import annotations

import atexit
import logging
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from gemstone_utils import election

from thaum.bots_registry import BOTS
from thaum import leader_init
from thaum.types import ServerConfig
from thaum.types import LogLevel
from log_setup import log_debug_blob

logger = logging.getLogger("thaum.leader_service")


@dataclass(frozen=True)
class LeaderTask:
    name: str
    interval_seconds: float
    fn: Callable[..., None]
    task_data: Any = None
    run_on_startup: bool = False


_tasks: List[LeaderTask] = []
_shutdown = threading.Event()
_loop_thread: Optional[threading.Thread] = None
_candidate_id: Optional[UUID] = None


def register_task(
    name: str,
    interval_seconds: float,
    fn: Callable[..., None],
    task_data: Any = None,
    *,
    run_on_startup: bool = False,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    _tasks.append(
        LeaderTask(
            name=name,
            interval_seconds=interval_seconds,
            fn=fn,
            task_data=task_data,
            run_on_startup=run_on_startup,
        )
    )


def build_maintenance_context(server_cfg: ServerConfig, config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "bots": BOTS,
        "server_cfg": server_cfg,
        "config": config,
    }


def run_startup_leader_tasks(server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    """
    Run maintenance tasks registered with ``run_on_startup=True`` once ``BOTS`` is populated.

    Call only on the election leader during bootstrap, after :func:`thaum.factory.initialize_bots`.
    Failures propagate (same as pre-bots leader init tasks).
    """
    ctx = build_maintenance_context(server_cfg, config)
    startup = [t for t in _tasks if t.run_on_startup]
    for i, t in enumerate(startup):
        logger.log(
            LogLevel.VERBOSE,
            "Leader maintenance startup run (%d/%d): %s",
            i + 1,
            len(startup),
            t.name,
        )
        try:
            t.fn(ctx, t.task_data)
        except Exception as e:
            logger.error("Leader maintenance startup task %r failed: %s", t.name, e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(
                    logger,
                    f"leader maintenance startup task traceback ({t.name})",
                    traceback.format_exc(),
                    LogLevel.SPAM,
                )
            raise
        logger.log(LogLevel.VERBOSE, "Leader maintenance startup task completed: %s", t.name)


def _run_due_tasks(
    server_cfg: ServerConfig,
    config: Dict[str, Any],
    last_run: Dict[str, float],
) -> None:
    if not _tasks:
        return
    now = time.monotonic()
    ctx = build_maintenance_context(server_cfg, config)
    for t in _tasks:
        prev = last_run.get(t.name, 0.0)
        if now - prev < t.interval_seconds:
            continue
        logger.log(LogLevel.VERBOSE, "Leader maintenance: task starting: %s", t.name)
        try:
            t.fn(ctx, t.task_data)
        except Exception as e:
            logger.error("Leader task %r failed: %s", t.name, e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(logger, f"leader task traceback ({t.name})", traceback.format_exc(), LogLevel.SPAM)
        finally:
            logger.log(LogLevel.VERBOSE, "Leader maintenance: task finished: %s", t.name)
        last_run[t.name] = now


def _leader_loop_body(server_cfg: ServerConfig, config: Dict[str, Any], cid: UUID) -> None:
    ns = server_cfg.election.namespace
    tick = float(server_cfg.election.heartbeat_seconds)
    last_run: Dict[str, float] = {}
    while not _shutdown.is_set():
        try:
            election.heartbeat(cid, ns)
            election.elect(cid, ns)
            if election.is_leader(cid, ns):
                _run_due_tasks(server_cfg, config, last_run)
        except Exception as e:
            logger.error("Leader loop tick failed: %s", e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(logger, "leader loop tick traceback", traceback.format_exc(), LogLevel.SPAM)
        if _shutdown.wait(timeout=tick):
            break


def start_leader_loop(
    server_cfg: ServerConfig,
    config: Dict[str, Any],
    *,
    candidate_id: Optional[UUID] = None,
    run_leader_loop: bool = True,
) -> None:
    """
    Start the election + maintenance daemon (skipped when ``run_leader_loop`` is False, e.g. tests).

    Pass ``candidate_id`` from :func:`thaum.leader_bootstrap.run_leader_bootstrap_phase` so this process
    does not register a second candidate; the background loop continues heartbeats/election only.
    """
    global _loop_thread, _candidate_id
    if not run_leader_loop:
        return
    if _loop_thread is not None and _loop_thread.is_alive():
        return

    election.set_expire(int(server_cfg.election.lease_seconds))
    if candidate_id is not None:
        cid = candidate_id
        _candidate_id = cid
    else:
        cid = uuid4()
        _candidate_id = cid
        election.register_candidate(cid, server_cfg.election.namespace)

    def _unregister() -> None:
        try:
            if _candidate_id is not None:
                election.unregister_candidate(_candidate_id, server_cfg.election.namespace)
        except Exception as e:
            logger.debug("unregister_candidate failed during shutdown: %s", e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(logger, "leader unregister traceback", traceback.format_exc(), LogLevel.SPAM)

    atexit.register(_unregister)

    def _run() -> None:
        _leader_loop_body(server_cfg, config, cid)

    _loop_thread = threading.Thread(
        target=_run,
        name="thaum-leader",
        daemon=True,
    )
    _loop_thread.start()
    logger.info("Leader election loop started (namespace=%r)", server_cfg.election.namespace)


def reset_for_tests() -> None:
    """Clear task registry and stop flag (unit tests)."""
    global _tasks, _shutdown, _loop_thread, _candidate_id
    _shutdown.set()
    if _loop_thread is not None:
        _loop_thread.join(timeout=2.0)
    _shutdown = threading.Event()
    _loop_thread = None
    _candidate_id = None
    _tasks = []
    leader_init.reset_for_tests()
