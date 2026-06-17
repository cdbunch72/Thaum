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
    """Configuration model for alert plugins loaded from ``[alerts.<plugin_name>]``.

    Attributes:
        plugin: Alert plugin module name under ``alerts.plugins``.
        status_mentions: When True, status webhook messages may use platform
            @-mentions (driver-dependent).
    """

    plugin: str
    # When True, status webhook messages may use platform @-mentions (driver-dependent).
    status_mentions: bool = True
    model_config = ConfigDict(extra="allow")
# -- End Class BaseAlertPluginConfig


class BaseAlertPlugin:
    """Base class for alert integrations.

    Plugins that expose status webhooks implement their own authorization logic.
    For integrations that only support a static Bearer value, use the canonical JSON
    pattern via :meth:`_validate_static_webhook_bearer` (see ``alerts.webhook_bearer``).

    Attributes:
        supports_status_webhooks: When True, the plugin registers inbound status
            webhook routes via :meth:`get_webhook_handlers`.
        supports_acknowledge: When True, the chat ``ack`` command and tracking-ID
            help text apply; integrations that cannot attribute ack to the
            requesting user should set False.
    """

    supports_status_webhooks: bool = False
    supports_acknowledge: bool = True
    _ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def __init__(self, config: BaseAlertPluginConfig):
        """Initialize the plugin with validated configuration.

        Args:
            config: Parsed alert plugin settings from TOML.
        """
        self.cfg = config
        self.logger = logging.getLogger(f"plugin.{self.__class__.__name__}")
    # -- End Method __init__

    def attach_bot(self, bot: "BaseChatBot") -> None:
        """Bind the owning chat bot and update the logger context.

        Args:
            bot: The chat bot instance that owns this alert plugin.
        """
        self.bot = bot
        self.logger = logging.getLogger(f"bot.{bot.handle}.plugin.{self.__class__.__name__}")
    # -- End Method attach_bot

    def get_webhook_handlers(self) -> Dict[str, Callable]:
        """Return HTTP route paths mapped to webhook handler callables.

        Returns:
            A dict of route suffix (e.g. ``"/webhook"``) to handler method.
            Override when :attr:`supports_status_webhooks` is True.
        """
        return {"/webhook": self.handle_status_webhook}
    # -- End Method get_webhook_handlers

    def _validate_static_webhook_bearer(
        self,
        authorization_header_value: Optional[str],
        configured_secret: str,
    ) -> bool:
        """Validate a static Bearer webhook using canonical JSON.

        Shared helper for integrations that compare the ``Authorization`` header
        against a configured secret (see ``alerts.webhook_bearer``).

        Args:
            authorization_header_value: Raw ``Authorization`` header value, or
                ``None`` when absent.
            configured_secret: Secret from plugin config. Use an empty string to
                disable verification (webhook open). Non-empty values are compared
                in constant time after canonicalization.

        Returns:
            True when verification passes or is disabled; False otherwise.
        """
        if configured_secret == "":
            return True
        bot_key = None
        if getattr(self, "bot", None) is not None:
            bot_key = getattr(self.bot, "bot_key", None) or getattr(self.bot, "handle", None)
        return _validate_webhook_bearer_plaintext(
            authorization_header_value=authorization_header_value,
            expected_secret_text=configured_secret,
            logger=self.logger,
            bot_key=bot_key,
        )
    # -- End Method _validate_static_webhook_bearer

    def validate_connection(self) -> bool:
        """Verify third-party API connectivity at startup.

        Returns:
            True when the integration is reachable and credentials are valid.

        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
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
        """Trigger an alert via the third-party API.

        Args:
            summary: Human-readable alert summary text.
            room_id: Chat room identifier where the alert was requested.
            sender: Person who initiated the alert.
            priority: Alert priority level (defaults to ``AlertPriority.NORMAL``).

        Returns:
            A tuple of ``(short_id, alert_id)``. ``short_id`` is a bot-local
            tracking token; ``alert_id`` is integration-specific (alias, vendor
            id, etc.) and may be ``None`` when not available without blocking.

        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
        raise NotImplementedError
    # -- End Method trigger_alert

    def acknowledge_alert(self, alias: str, person: ThaumPerson) -> None:
        """Acknowledge an open alert on behalf of a person.

        Optional hook for integrations that support ack. Override when
        :attr:`supports_acknowledge` is True.

        Args:
            alias: Integration-specific alert identifier or short tracking id.
            person: Person performing the acknowledgment.
        """
        self.logger.debug("acknowledge_alert not implemented (%s, %s)", alias, person.for_display)
    # -- End Method acknowledge_alert

    def handle_status_webhook(self, request_data: Dict[str, Any]) -> None:
        """Handle an inbound status webhook payload.

        Default no-op handler for the ``/webhook`` route. Override when the
        integration receives asynchronous status updates.

        Args:
            request_data: Parsed webhook body (structure is integration-specific).
        """
        self.logger.debug("Received status webhook, but no handler implemented.")
    # -- End Method handle_status_webhook

# -- End Class BaseAlertPlugin
