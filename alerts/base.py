# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# alerts/base.py
import logging
from typing import Any, Callable, Dict, Optional, Tuple, TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict

from thaum.types import AlertPriority, ThaumPerson
from alerts.webhook_bearer import validate_webhook_bearer as _validate_webhook_bearer_plaintext
import secrets

if TYPE_CHECKING:
    from bots.base import BaseChatBot


class BaseAlertPluginConfig(BaseModel):
    plugin: str
    # When True, status webhook messages may use platform @-mentions (driver-dependent).
    status_mentions: bool = True
    model_config = ConfigDict(extra="allow")
# -- End Class BaseAlertPluginConfig


class BaseAlertPlugin:
    """
    Base class for alert integrations.

    Plugins that expose status webhooks implement their own authorization logic.
    For integrations that only support a static Bearer value, use the canonical JSON
    pattern via `_validate_static_webhook_bearer` (see `alerts.webhook_bearer`).
    """

    supports_status_webhooks: bool = False
    _ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def __init__(self, config: BaseAlertPluginConfig):
        self.cfg = config
        self.logger = logging.getLogger(f"plugin.{self.__class__.__name__}")
    # -- End Method __init__

    def attach_bot(self, bot: "BaseChatBot") -> None:
        """Binds the bot and updates the logger context."""
        self.bot = bot
        self.logger = logging.getLogger(f"bot.{bot.name}.plugin.{self.__class__.__name__}")
    # -- End Method attach_bot

    def get_webhook_handlers(self) -> Dict[str, Callable]:
        """Returns a map of routes to methods."""
        return {"/webhook": self.handle_status_webhook}
    # -- End Method get_webhook_handlers

    def _validate_static_webhook_bearer(
        self,
        authorization_header_value: Optional[str],
        configured_secret: str,
    ) -> bool:
        """
        Shared helper for static Bearer webhooks using canonical JSON (`webhook_bearer`).

        `configured_secret` must be present in the plugin config when the plugin uses
        this pattern: use an empty string to disable verification (webhook open).
        Non-empty values are compared in constant time after canonicalization.
        """
        if configured_secret == "":
            return True
        bot_key = None
        if getattr(self, "bot", None) is not None:
            bot_key = getattr(self.bot, "bot_key", None) or getattr(self.bot, "name", None)
        return _validate_webhook_bearer_plaintext(
            authorization_header_value=authorization_header_value,
            expected_secret_text=configured_secret,
            logger=self.logger,
            bot_key=bot_key,
        )
    # -- End Method _validate_static_webhook_bearer

    def validate_connection(self) -> bool:
        """Verify API connectivity at boot."""
        raise NotImplementedError
    # -- End Method validate_connection

    @classmethod
    def _generate_short_id(cls, length: int = 4) -> str:
        return "".join(secrets.choice(cls._ALPHABET) for _ in range(length))
    # -- End Method _generate_short_id

    def trigger_alert(
        self,
        summary: str,
        room_id: str,
        sender: ThaumPerson,
        priority=AlertPriority.NORMAL,
    ) -> Tuple[str, Optional[str]]:
        """
        Trigger an alert via the 3rd party API.

        Returns ``(short_id, alert_id)``. ``alert_id`` is integration-specific (alias, vendor id, etc.)
        and may be ``None`` when not available without blocking.
        """
        raise NotImplementedError
    # -- End Method trigger_alert

    def acknowledge_alert(self, alias: str, person_name: str) -> None:
        """Optional: integrations that support ack should override."""
        self.logger.debug("acknowledge_alert not implemented (%s, %s)", alias, person_name)
    # -- End Method acknowledge_alert

    def handle_status_webhook(self, request_data: Dict[str, Any]) -> None:
        """Default handler for /webhook path."""
        self.logger.debug("Received status webhook, but no handler implemented.")
    # -- End Method handle_status_webhook

# -- End Class BaseAlertPlugin
