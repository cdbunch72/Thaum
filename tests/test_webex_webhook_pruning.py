"""Tests for Webex webhook pruning behavior."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from bots.plugins.webex_bot import WebexChatBot


def _make_bot(endpoint: str, existing_hooks: list[SimpleNamespace]) -> WebexChatBot:
    bot = WebexChatBot.__new__(WebexChatBot)
    bot.endpoint = endpoint
    bot.name = "TestBot"
    bot.bot_key = "test-bot"
    bot.logger = MagicMock()
    bot._webhook_ids = None
    bot._webhook_secret_for_api = lambda: None

    webhooks = MagicMock()
    webhooks.list.return_value = existing_hooks
    webhooks.create.side_effect = [
        SimpleNamespace(id="created-messages"),
        SimpleNamespace(id="created-actions"),
    ]
    api = MagicMock()
    api.webhooks = webhooks
    bot.api = api
    return bot


class WebexWebhookPruningTests(unittest.TestCase):
    def test_prune_deletes_http_variant_when_target_is_https(self) -> None:
        hooks = [
            SimpleNamespace(id="old-http", targetUrl="http://example.com/bot/test-bot"),
            SimpleNamespace(id="keep-other", targetUrl="https://other.example.com/bot/test-bot"),
        ]
        bot = _make_bot("https://example.com/bot/test-bot", hooks)

        bot.register_bot_webhook()

        bot.api.webhooks.delete.assert_called_once_with("old-http")

    def test_prune_deletes_https_variant_when_target_is_http(self) -> None:
        hooks = [
            SimpleNamespace(id="old-https", targetUrl="https://example.com/bot/test-bot"),
            SimpleNamespace(id="keep-other", targetUrl="http://example.com/bot/other-bot"),
        ]
        bot = _make_bot("http://example.com/bot/test-bot", hooks)

        bot.register_bot_webhook()

        bot.api.webhooks.delete.assert_called_once_with("old-https")

    def test_prune_keeps_different_path(self) -> None:
        hooks = [
            SimpleNamespace(id="different-path", targetUrl="https://example.com/bot/other-bot"),
        ]
        bot = _make_bot("https://example.com/bot/test-bot", hooks)

        bot.register_bot_webhook()

        bot.api.webhooks.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
