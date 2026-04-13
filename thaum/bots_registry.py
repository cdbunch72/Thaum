# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# thaum/bots_registry.py
"""Runtime bot map; lives outside :mod:`thaum.factory` to avoid importing ``bots.base`` during ``thaum`` package load."""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from bots.base import BaseChatBot

BOTS: Dict[str, 'BaseChatBot'] = {}
