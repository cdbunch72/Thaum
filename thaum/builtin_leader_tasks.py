# thaum/builtin_leader_tasks.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import delete

from gemstone_utils.db import get_session

from thaum.admin_models import AdminLogNonce
from thaum.database_crypto import (
    progressive_reencrypt_encrypted_strings_if_needed,
    rotate_data_encryption_key_if_due,
)
from thaum.types import ServerConfig


def register_builtin_tasks(
    registry: Any,
    *,
    server_cfg: ServerConfig,
    config: Dict[str, Any],
) -> None:
    def purge_admin_nonces(ctx: Any, task_data: Any) -> None:
        now = datetime.now(timezone.utc)
        with get_session() as session:
            with session.begin():
                session.execute(delete(AdminLogNonce).where(AdminLogNonce.expires_at < now))

    registry.register_task("admin_log_nonce_gc", 3600.0, purge_admin_nonces)

    def dek_rotate(ctx: Any, task_data: Any) -> None:
        rotate_data_encryption_key_if_due(ctx["server_cfg"])

    registry.register_task("thaum_dek_rotation", 3600.0, dek_rotate)

    def encrypted_field_catchup(ctx: Any, task_data: Any) -> None:
        progressive_reencrypt_encrypted_strings_if_needed(ctx["server_cfg"])

    registry.register_task("thaum_encrypted_field_catchup", 300.0, encrypted_field_catchup)
