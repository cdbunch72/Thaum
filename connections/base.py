# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# connections/base.py
"""Shared base types for connection config plugins (Atlassian Cloud, future providers)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BaseConnectionConfig(BaseModel):
    """
    Discriminated connection profile loaded from ``[connections.<name>]`` in config.

    Concrete plugins set ``plugin`` to a fixed literal (e.g. ``\"atlassian\"``).
    Fields may be optional at this layer; merged configs (connection → defaults →
    consumer) are validated again by each consumer.
    """

    plugin: str = Field(..., description="Connection plugin id (e.g. atlassian).")

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

# -- End Class BaseConnectionConfig
