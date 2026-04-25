# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_handlers_incident_prompt_card.py
"""Tests for configurable help/emergency incident prompt cards."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from thaum.handlers import _incident_prompt_card


class IncidentPromptCardTemplateTest(unittest.TestCase):
    def _mk_bot(self, inline: str | None = None, template_path: str | None = None):
        return SimpleNamespace(
            incident_prompt_card_template=inline,
            incident_prompt_card_template_path=template_path,
        )

    def test_default_card_used_when_no_template_configured(self) -> None:
        bot = self._mk_bot()
        card = _incident_prompt_card(
            bot,
            team_description="Database",
            default_high_priority=False,
            show_priority_toggle=False,
        )
        self.assertEqual(card["type"], "AdaptiveCard")
        self.assertEqual(card["actions"][0]["data"]["is_emergency"], "false")
        self.assertEqual(card["body"][1]["id"], "summary")

    def test_renders_from_template_path(self) -> None:
        with TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "incident_prompt_card.j2"
            template_path.write_text(
                """
{
  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.3",
  "body": [{"type":"TextBlock","text":{{ team_description | tojson }}}],
  "actions": [{"type":"Action.Submit","title":"Submit","data":{"action":"submit_incident"}}]
}
""".strip(),
                encoding="utf-8",
            )
            bot = self._mk_bot(template_path=str(template_path))
            card = _incident_prompt_card(
                bot,
                team_description="SRE",
                default_high_priority=False,
                show_priority_toggle=False,
            )
        self.assertEqual(card["body"][0]["text"], "SRE")

    def test_malformed_template_falls_back_to_default_card(self) -> None:
        inline = '{"$schema":"http://adaptivecards.io/schemas/adaptive-card.json","type":"AdaptiveCard","version":"1.3","body":[{"type":"TextBlock","text":{{ missing_var | tojson }}}],"actions":[]}'
        bot = self._mk_bot(inline=inline)
        card = _incident_prompt_card(
            bot,
            team_description="Network",
            default_high_priority=False,
            show_priority_toggle=False,
        )
        self.assertEqual(card["body"][0]["type"], "TextBlock")
        self.assertEqual(card["body"][1]["id"], "summary")

    def test_toggle_value_uses_priority_in_template(self) -> None:
        inline = """
{
  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.3",
  "body": [
    {
      "type": "Input.Toggle",
      "id": "is_emergency",
      "value": {{ ("true" if default_high_priority else "false") | tojson }},
      "valueOn": "true",
      "valueOff": "false"
    }
  ],
  "actions": [{"type":"Action.Submit","title":"Submit","data":{"action":"submit_incident"}}]
}
""".strip()
        bot = self._mk_bot(inline=inline)
        card = _incident_prompt_card(
            bot,
            team_description="SRE",
            default_high_priority=True,
            show_priority_toggle=True,
        )
        self.assertEqual(card["body"][0]["value"], "true")


if __name__ == "__main__":
    unittest.main()
