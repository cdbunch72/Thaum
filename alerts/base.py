# alerts/base.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import json
import base64
import hmac
import hashlib
import time
import logging
from typing import Dict, Any, Callable, Optional

class BaseAlertPlugin:
    """
    The Base Class for all Thaum alert integrations.
    This provides the security boundary (token validation) inherited by all plugins.
    """
    
    supports_status_webhooks: bool = False

    def __init__(self, **config: Any):
        self.config = config
        self.logger = logging.getLogger(f"plugin.{self.__class__.__name__}")
    # -- End Method __init__

    def attach_bot(self, bot) -> None:
        """Binds the bot and updates the logger context."""
        self.bot = bot
        self.logger = logging.getLogger(f"bot.{bot.name}.plugin.{self.__class__.__name__}")
    # -- End Method attach_bot

    def get_webhook_handlers(self) -> Dict[str, Callable]:
        """
        Returns a map of routes to methods.
        Plugins can override this to register multiple endpoints.
        """
        return {'/webhook': self.handle_status_webhook}
    # -- End Method get_webhook_handlers

    def _validate_thaum_token(self, token_str: str, hmac_key: str) -> bool:
        """
        INTERNAL SECURITY GATEKEEPER.
        Inherited by plugins to ensure consistent auth logic.
        """
        FOREVER = 0 
        try:
            raw = base64.urlsafe_b64decode(token_str.encode())
            sig, payload_json = raw[:32], raw[32:]
            
            # Verify signature
            expected_sig = hmac.new(hmac_key.encode(), payload_json, hashlib.sha256).digest()
            if not hmac.compare_digest(sig, expected_sig):
                self.logger.warning("Auth attempt failed: Token signature mismatch.")
                return False
                
            payload: Dict[str, Any] = json.loads(payload_json)
            exp = payload.get("exp", 1)
            
            # Check expiry
            return exp == FOREVER or time.time() < exp
            
        except Exception as e:
            self.logger.error(f"Token validation crashed: {e}")
            return False
    # -- End Method _validate_thaum_token

    def validate_connection(self) -> bool:
        """Verify API connectivity at boot."""
        raise NotImplementedError
    # -- End Method validate_connection

    def trigger_alert(self, summary: str, is_emergency: bool, room_id: str) -> str:
        """Trigger an alert via the 3rd party API."""
        raise NotImplementedError
    # -- End Method trigger_alert

    def handle_status_webhook(self, request_data: Dict[str, Any]) -> None:
        """Default handler for /webhook path."""
        self.logger.debug("Received status webhook, but no handler implemented.")
        pass
    # -- End Method handle_status_webhook

# -- End Class BaseAlertPlugin