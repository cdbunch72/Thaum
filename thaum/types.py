# thaum/types.py
# Thaum
# Copyright 2026, Clinton Bunch. All Rights Reserved
# SPDX-License-Identifier: MPL-2.0
# This file source licensed under the Mozilla Public License 2.0

import time
import os
from pathlib import Path
from pydantic import ConfigDict, model_validator, BaseModel, SecretStr, BeforeValidator
from typing import Optional, Annotated, Dict, List, TYPE_CHECKING
from enum import StrEnum,IntEnum,auto
from emerald_utils.experimental.secrets_resolver import resolve_secret
import logging
import verboselogs
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from bots.base import BaseChatBot

ResolvedSecret = Annotated[SecretStr, BeforeValidator(resolve_secret)]

logger = logging.getLogger("thaum.types")

BaseUrlSource = StrEnum(
    "BaseUrlSource",
    ["CONFIG", "ENVIRONMENT", "GOOGLE", "AZURE", "AWS"],
)


def _resolve_base_url(config_base_url: Optional[str]) -> tuple[str, BaseUrlSource]:
    """
    Returns the resolved URL and its source of truth.
    Strict fail-fast implementation.
    """
    if config_base_url:
        return config_base_url.rstrip('/'), BaseUrlSource.CONFIG

    if env_url := os.environ.get("THAUM_BASE_URL"):
        return env_url.rstrip('/'), BaseUrlSource.ENVIRONMENT

    if "K_SERVICE" in os.environ:
        return os.environ.get("K_SERVICE_URL", "").rstrip('/'), BaseUrlSource.GOOGLE

    if "WEBSITE_HOSTNAME" in os.environ:
        return f"https://{os.environ['WEBSITE_HOSTNAME']}".rstrip('/'), BaseUrlSource.AZURE

    if "AWS_APP_RUNNER_SERVICE_URL" in os.environ:
        return os.environ["AWS_APP_RUNNER_SERVICE_URL"].rstrip('/'), BaseUrlSource.AWS

    logger.critical("No base_url configured and no cloud environment detected.")
    raise ValueError("System cannot determine public Base URL. Configure base_url or THAUM_BASE_URL.")

class LogLevel(IntEnum):
    SPAM     = verboselogs.SPAM
    DEBUG    = logging.DEBUG
    VERBOSE  = verboselogs.VERBOSE
    INFO     = logging.INFO
    NOTICE   = verboselogs.NOTICE
    WARNING  = logging.WARNING
    ERROR    = logging.ERROR
    CRITICAL = logging.CRITICAL
class AlertPriority(StrEnum):
    NORMAL = auto()
    HIGH   = auto()

@dataclass
class ThaumPerson:
    email: str
    display_name: Optional[str] = None
    platform_ids: Dict[str, str] = field(default_factory=dict)
    source_plugin: str = "unknown"

    @property
    def for_display(self) -> str:
        if self.display_name:
            return self.display_name
        return self.email


@dataclass
class ThaumTeam:
    bot: 'BaseChatBot'
    team_name: str

    lookup_id: str | None = None     # DN or canonical directory key
    alert_id: str | None = None      # Jira team ID

    _members: list[ThaumPerson] = field(default_factory=list)
    last_cached: float = field(default_factory=time.time)
    ttl: int = 14400  # 4 hours

    @property
    def is_fresh(self) -> bool:
        return (time.time() - self.last_cached) < self.ttl

    def get_members(self) -> list[ThaumPerson]:
        """Return members, refreshing from lookup plugin if stale."""
        lookup = self.bot.lookup_plugin

        if not self.is_fresh and lookup is not None:
            try:
                new_members = lookup.lookup_team_members(self)
                if new_members:
                    self._members = new_members
                    self.last_cached = time.time()
            except Exception as e:
                # Log through the bot
                self.bot.log.warning(f"Failed to refresh membership for team '{self.team_name}': {e}")

        return list(self._members)
# -- End ThaumTeam

@dataclass
class RespondersList:
    people: List[ThaumPerson] = field(default_factory=list)
    teams: List[ThaumTeam] = field(default_factory=list)

    def get_responders(self) -> List[ThaumPerson]:
        responders = list(self.people)
        for team in self.teams:
            responders.extend(team.get_members())
        return responders

    def __add__(self, other: object) -> "RespondersList":
        if isinstance(other, RespondersList):
            return RespondersList(
                people=[*self.people, *other.people],
                teams=[*self.teams, *other.teams],
            )
        if isinstance(other, ThaumPerson):
            return RespondersList(people=[*self.people, other], teams=list(self.teams))
        if isinstance(other, ThaumTeam):
            return RespondersList(people=list(self.people), teams=[*self.teams, other])
        return NotImplemented

    def __radd__(self, other: object) -> "RespondersList":
        if other == 0:
            return self
        return self.__add__(other)
# -- End RespondersList

# -- Pydantic config classes
class ServerConfig(BaseModel):
    base_url: str
    url_source: Optional[BaseUrlSource] = None
    bot_url_prefix: Optional[str] = '/bot'
    bot_type: str
    lookup_plugin: str = "null"
    # Runtime log override reloader.
    # If > 0, workers automatically re-apply the override when the override file changes.
    # Default enables polling once per second.
    log_override_poll_seconds: float = 1.0
    log_override_watchdog: bool = False
    log_override_path: str = "/run/thaum/log_override"
    # Shared runtime state (webhook bearer warn markers, etc.); must be absolute.
    thaum_state_dir: str = "/run/thaum"
    model_config = ConfigDict(
        extra='forbid',          # Reject extra keys in TOML (Prevents typos)
        #frozen=True,             # Make the config immutable after load (Safety!)
        validate_assignment=True # Validate if someone changes a value after boot
    )
    @model_validator(mode='after')
    def resolve_url(self) -> 'ServerConfig':
        # This function runs after fields are set
        (self.base_url,self.url_source) = _resolve_base_url(self.base_url)
        return self
    # -- End resolve_url

    @model_validator(mode='after')
    def resolve_thaum_state_dir(self) -> 'ServerConfig':
        p = Path(self.thaum_state_dir)
        if not p.is_absolute():
            raise ValueError("server.thaum_state_dir must be an absolute path")
        self.thaum_state_dir = str(p)
        return self
    # -- End resolve_thaum_state_dir
# -- End ServerConfig

class LogConfig(BaseModel):
    level: LogLevel =  LogLevel.INFO
    timezone: str = "UTC"
    no_timestamp: bool = False
    fractional_seconds: bool = False
    model_config = ConfigDict(
        extra='forbid',          # Reject extra keys in TOML (Prevents typos)
        frozen=True,             # Make the config immutable after load (Safety!)
        validate_assignment=True # Validate if someone changes a value after boot
    )
# -- End LogConfig