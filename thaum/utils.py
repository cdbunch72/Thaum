from enum import Enum, auto
from typing import Tuple, Optional
from thaum.types import BaseUrlSource
import os
import logging

logger = logging.getLogger("thaum.utils")


def resolve_base_url(config_base_url: Optional[str]) -> Tuple[str, BaseUrlSource]:
    """
    Returns the resolved URL and its source of truth.
    Strict fail-fast implementation.
    """
    
    # 1. Config explicit override
    if config_base_url:
        return config_base_url.rstrip('/'), BaseUrlSource.CONFIG

    # 2. Environment Variable override
    if env_url := os.environ.get("THAUM_BASE_URL"):
        return env_url.rstrip('/'), BaseUrlSource.ENVIRONMENT
        
    # 3. Cloud Auto-Detection
    if "K_SERVICE" in os.environ:
        return os.environ.get("K_SERVICE_URL", "").rstrip('/'), BaseUrlSource.GOOGLE
    
    if "WEBSITE_HOSTNAME" in os.environ:
        return f"https://{os.environ['WEBSITE_HOSTNAME']}".rstrip('/'), BaseUrlSource.AZURE
        
    if "AWS_APP_RUNNER_SERVICE_URL" in os.environ:
        return os.environ['AWS_APP_RUNNER_SERVICE_URL'].rstrip('/'), BaseUrlSource.AWS

    # 4. Strict Failure (No magic defaults unless you choose to add them)
    logger.critical("No base_url configured and no cloud environment detected.")
    raise ValueError("System cannot determine public Base URL. Configure base_url or THAUM_BASE_URL.")
# -- End Function resolve_base_url