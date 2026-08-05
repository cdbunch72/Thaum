# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# connections/plugins/atlassian.py
"""Atlassian Cloud connection: site, Cloud id, org id, optional API user/token."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, field_validator

from connections.base import BaseConnectionConfig
from thaum.https_url import normalize_https_base_url
from thaum.types import OptionalResolvedSecret


class AtlassianConnectionConfig(BaseConnectionConfig):
    """
    Official Atlassian Cloud identity material (Teams API, Jira REST, etc.).

    ``user`` / ``api_token`` may be omitted here and supplied via defaults or
    per-bot / per-plugin tables when credentials differ by integration.
    """

    plugin: Literal["atlassian"] = "atlassian"

    site_url: OptionalResolvedSecret = Field(
        default=None,
        description="Jira/Confluence site base URL, e.g. https://your-site.atlassian.net",
    )
    cloud_id: OptionalResolvedSecret = Field(
        default=None,
        description="Atlassian Cloud UUID (site id) for api.atlassian.com paths.",
    )
    org_id: OptionalResolvedSecret = Field(
        default=None,
        description="Atlassian organization id (Public Teams and org-scoped APIs).",
    )
    user: OptionalResolvedSecret = Field(
        default=None,
        description="Account email for REST API token auth (Basic).",
    )
    api_token: OptionalResolvedSecret = Field(
        default=None,
        description="API token for ``user`` (Basic auth to site REST and compatible endpoints).",
    )

    @field_validator("site_url", mode="after")
    @classmethod
    def _normalize_site_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return v
        return normalize_https_base_url(str(v))

# -- End Class AtlassianConnectionConfig


def get_config_model():
    return AtlassianConnectionConfig
