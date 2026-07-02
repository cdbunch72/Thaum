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
    def _mk_bot(
        self,
        inline: str | None = None,
        template_path: str | None = None,
        *,
        base_url: str = "",
        handle: str = "TestBot",
        team_description: str = "Database",
        display_name: str | None = None,
        phone_number: str | None = None,
        card_extra_text_template: str | None = None,
        send_alerts: bool = False,
        high_pri_on: bool = False,
    ):
        return SimpleNamespace(
            incident_prompt_card_template=inline,
            incident_prompt_card_template_path=template_path,
            base_url=base_url,
            handle=handle,
            team_description=team_description,
            display_name=display_name,
            phone_number=phone_number,
            card_extra_text_template=card_extra_text_template,
            send_alerts=send_alerts,
            high_pri_on=high_pri_on,
        )

    def test_default_card_used_when_no_template_configured(self) -> None:
        bot = self._mk_bot()
        card = _incident_prompt_card(bot, default_high_priority=False)
        self.assertEqual(card["type"], "AdaptiveCard")
        self.assertNotIn("is_emergency", card["actions"][0]["data"])
        self.assertEqual(card["body"][1]["type"], "ColumnSet")
        self.assertEqual(card["body"][4]["id"], "summary")
        toggle = card["body"][5]
        self.assertEqual(toggle["type"], "Input.Toggle")
        self.assertEqual(toggle["id"], "is_emergency")
        self.assertFalse(toggle["isVisible"])

    def test_default_card_toggle_visible_when_enabled(self) -> None:
        bot = self._mk_bot(high_pri_on=True)
        card = _incident_prompt_card(bot, default_high_priority=False)
        self.assertTrue(card["body"][5]["isVisible"])
        self.assertNotIn("is_emergency", card["actions"][0]["data"])

    def test_default_card_bot_name_from_display_name(self) -> None:
        bot = self._mk_bot(display_name="Myrddin Helpdesk", handle="Myrddin")
        card = _incident_prompt_card(bot, default_high_priority=False)
        bot_col = card["body"][1]["columns"][1]["items"][0]
        self.assertEqual(bot_col["text"], "Myrddin Helpdesk")

    def test_default_card_bot_name_falls_back_to_handle(self) -> None:
        bot = self._mk_bot(handle="Myrddin")
        card = _incident_prompt_card(bot, default_high_priority=False)
        bot_col = card["body"][1]["columns"][1]["items"][0]
        self.assertEqual(bot_col["text"], "Myrddin")

    def test_default_card_phone_row_visible_when_set(self) -> None:
        bot = self._mk_bot(phone_number="1-800-HELP-DESK (1-800-435-7335)")
        card = _incident_prompt_card(bot, default_high_priority=False)
        phone_row = card["body"][2]
        self.assertTrue(phone_row["isVisible"])
        phone_col = phone_row["columns"][1]["items"][0]
        self.assertEqual(phone_col["text"], "1-800-HELP-DESK (1-800-435-7335)")

    def test_default_card_phone_row_hidden_when_unset(self) -> None:
        bot = self._mk_bot()
        card = _incident_prompt_card(bot, default_high_priority=False)
        self.assertFalse(card["body"][2]["isVisible"])

    def test_extra_card_text_rendered_from_template(self) -> None:
        bot = self._mk_bot(
            send_alerts=False,
            card_extra_text_template="Reach {{ bot_name }} for {{ team_description }}.",
            display_name="Desk Bot",
        )
        card = _incident_prompt_card(bot, default_high_priority=False)
        extra = card["body"][3]
        self.assertTrue(extra["isVisible"])
        self.assertEqual(extra["text"], "Reach Desk Bot for Database.")

    def test_extra_card_text_can_use_send_alerts(self) -> None:
        bot = self._mk_bot(
            send_alerts=True,
            card_extra_text_template="{% if send_alerts %}On-call will be paged.{% endif %}",
        )
        card = _incident_prompt_card(bot, default_high_priority=False)
        self.assertEqual(card["body"][3]["text"], "On-call will be paged.")

    def test_extra_card_text_render_failure_falls_back_to_empty(self) -> None:
        bot = self._mk_bot(card_extra_text_template="{{ undefined_var }}")
        card = _incident_prompt_card(bot, default_high_priority=False)
        self.assertFalse(card["body"][3]["isVisible"])
        self.assertEqual(card["body"][3]["text"], "")

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
            bot = self._mk_bot(template_path=str(template_path), team_description="SRE")
            card = _incident_prompt_card(bot, default_high_priority=False)
        self.assertEqual(card["body"][0]["text"], "SRE")

    def test_sample_template_renders_logo_and_identity_rows(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        sample_path = repo_root / "incident_prompt_card.sample.j2"
        bot = self._mk_bot(
            template_path=str(sample_path),
            base_url="https://thaum.example.com",
            display_name="SRE Bot",
            phone_number="555-0100",
            team_description="SRE",
            high_pri_on=True,
        )
        card = _incident_prompt_card(bot, default_high_priority=False)
        self.assertEqual(card["body"][0]["type"], "Image")
        self.assertEqual(
            card["body"][0]["url"],
            "https://thaum.example.com/static/Thaum_wizard_cgi.jpg",
        )
        self.assertEqual(card["body"][2]["type"], "ColumnSet")
        phone_row = card["body"][3]
        self.assertTrue(phone_row["isVisible"])
        self.assertEqual(card["body"][5]["id"], "summary")
        self.assertEqual(card["body"][6]["id"], "is_emergency")

    def test_malformed_template_falls_back_to_default_card(self) -> None:
        inline = '{"$schema":"http://adaptivecards.io/schemas/adaptive-card.json","type":"AdaptiveCard","version":"1.3","body":[{"type":"TextBlock","text":{{ missing_var | tojson }}}],"actions":[]}'
        bot = self._mk_bot(inline=inline, team_description="Network")
        card = _incident_prompt_card(bot, default_high_priority=False)
        self.assertEqual(card["body"][0]["type"], "TextBlock")
        self.assertEqual(card["body"][4]["id"], "summary")

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
        card = _incident_prompt_card(bot, default_high_priority=True)
        self.assertEqual(card["body"][0]["value"], "true")


if __name__ == "__main__":
    unittest.main()
