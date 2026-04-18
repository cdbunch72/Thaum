# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/leader_bootstrap.py
"""Synchronous election + leader-only bootstrap tasks before ``initialize_bots``."""
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict
from uuid import UUID, uuid4

from gemstone_utils import election
from gemstone_utils.db import get_session

from thaum.leader_init import (
    mark_leader_init_done,
    mark_leader_init_failed,
    mark_leader_init_running,
    run_registered_init_tasks,
    wait_for_leader_init_barrier,
)
from thaum.types import LogLevel, ServerConfig
from log_setup import log_debug_blob

logger = logging.getLogger("thaum.leader_bootstrap")


def run_leader_bootstrap_phase(server_cfg: ServerConfig, config: Dict[str, Any]) -> UUID:
    """
    Register with election, run one heartbeat/elect cycle, then:

    - **Leader**: DB barrier RUNNING → registered init tasks → DONE or FAILED.
    - **Non-leader**: block until leader reports DONE (or FAILED / timeout).

    Returns the candidate id for :func:`thaum.leader_service.start_leader_loop`.
    """
    ns = server_cfg.election.namespace
    election.set_expire(int(server_cfg.election.lease_seconds))
    cid = uuid4()
    election.register_candidate(cid, ns)
    election.heartbeat(cid, ns)
    election.elect(cid, ns)

    if election.is_leader(cid, ns):
        logger.info("This worker is election leader; running leader init tasks.")
        with get_session() as session:
            with session.begin():
                mark_leader_init_running(session)
        try:
            run_registered_init_tasks(server_cfg, config)
        except Exception as e:
            logger.error("Leader init tasks failed: %s", e)
            if logger.isEnabledFor(LogLevel.SPAM):
                log_debug_blob(logger, "leader init tasks traceback", traceback.format_exc(), LogLevel.SPAM)
            with get_session() as session:
                with session.begin():
                    mark_leader_init_failed(session, str(e))
            raise
        with get_session() as session:
            with session.begin():
                mark_leader_init_done(session)
    else:
        logger.info("Not election leader; waiting for leader init barrier.")
        wait_for_leader_init_barrier(server_cfg)

    return cid
