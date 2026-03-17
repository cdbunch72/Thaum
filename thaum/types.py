# Thaum
# Copyright 2026, Clinton Bunch.  All Rights Reserved
# This file source licensed under the Mozilla Public License 2.0

import time
from  pydantic import ConfigDict, PrivateAttr,model_validator,BaseModel
from typing import Optional,Tuple
from enum import StrEnum,IntEnum
from thaum.utils import resolve_base_url
import logging
import verboselogs
from dataclasses import dataclass, field
from typing import Dict, List, Optional,TYPE_CHECKING

if TYPE_CHECKING:
    from bots.base import BaseChatBot

BaseUrlSource=StrEnum('BaseUrlSource',["CONFIG","ENVIRONMENT","GOOGLE","AZURE","AWS"])
class LogLevel(IntEnum):
    SPAM     = verboselogs.SPAM
    DEBUG    = logging.DEBUG
    VERBOSE  = verboselogs.VERBOSE
    INFO     = logging.INFO
    NOTICE   = verboselogs.NOTICE
    WARNING  = logging.WARNING
    ERROR    = logging.ERROR
    CRITICAL = logging.CRITICAL

@dataclass
class ThaumPerson:
    email: str
    display_name: str
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
    members: List[ThaumPerson] = field(default_factory=list)
    last_cached: float = field(default_factory=time.time)
    ttl: int = 14400 

    @property
    def is_fresh(self) -> bool:
        return (time.time() - self.last_cached) < self.ttl
# -- End ThaumTeam

# -- Pydantic config classes
class ServerConfig(BaseModel):
    base_url: str
    url_source: Optional[BaseUrlSource] = None
    bot_url_prefix: Optional[str] = '/bot'
    bot_type: str
    model_config = ConfigDict(
        extra='forbid',          # Reject extra keys in TOML (Prevents typos)
        #frozen=True,             # Make the config immutable after load (Safety!)
        validate_assignment=True # Validate if someone changes a value after boot
    )
    @model_validator(mode='after')
    def resolve_url(self) -> 'ServerConfig':
        # This function runs after fields are set
        (self.base_url,self.url_source) = resolve_base_url(self.base_url)
        return self
    # -- End resolve_url
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