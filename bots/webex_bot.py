# bots/webex_bot.py
# Thaum Engine v1.0.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import logging
from typing import Dict, Any, Optional, List
from thaum.identity import ThaumPerson
from webexpythonsdk import WebexAPI
from bots.base import BaseBot

class WebexBot(BaseBot):
    """Concrete driver for Webex."""

    def __init__(self, name: str, endpoint: str, token: str, secret: Optional[str]):
        super().__init__(name, endpoint)
        self.logger = logging.getLogger(f"bot.{name}")
        self.api = WebexAPI(access_token=token)
        self.me = self.api.people.me()
        self.secret = secret
        self.responders: List[str] = []
        
        # Internal state for bot behavior
        self._hears_routes = []
    # -- End Method __init__

    def say(self, room_id: str, text: str, markdown: Optional[str] = None) -> None:
        self.api.messages.create(roomId=room_id, text=text, markdown=markdown)
    # -- End Method say

    def send_card(self, room_id: str, card_content: dict, fallback_text: str = "Adaptive Card") -> None:
        attachment = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card_content
        }
        self.api.messages.create(roomId=room_id, text=fallback_text, attachments=[attachment])
    # -- End Method send_card

    def create_room(self, title: str) -> str:
        room = self.api.rooms.create(title=title)
        return room.id
    # -- End Method create_room

    def add_members(self, room_id: str, members: List[ThaumPerson]) -> None:
        for m in members:
            # Logic: '@' in string indicates email, else assume personId
            key = "personEmail" if "@" in m else "personId"
            try:
                self.api.memberships.create(roomId=room_id, **{key: m})
            except Exception as e:
                self.logger.error(f"Failed to add {m} to {room_id}: {e}")
    # -- End Method add_members

    def delete_room(self, room_id: str) -> None:
        self.api.rooms.delete(room_id)
        self.logger.info(f"Room {room_id} imploded.")
    # -- End Method delete_room

    def validate_signature(self, payload_body: bytes, signature: Optional[str]) -> bool:
        if self.secret is None: return True
        if not signature: return False
        
        import hmac, hashlib
        hashed = hmac.new(self.secret.encode(), payload_body, hashlib.sha1)
        return hmac.compare_digest(hashed.hexdigest(), signature)
    # -- End Method validate_signature

    def process_message(self, message_id: str) -> Optional[str]:
        """
        Fetches the message and returns the clean text ONLY if 
        it's a DM or a mention. Otherwise returns None.
        """
        message = self.api.messages.get(message_id)
        
        # 1. DM Check
        room = self.api.rooms.get(message.roomId)
        is_direct = (room.type == "direct")
        
        # 2. Mention Check
        is_mentioned = message.mentionedPeople and self.me.id in message.mentionedPeople
        
        if not (is_direct or is_mentioned):
            return None # Ignore this message
            
        # 3. Clean the text (strip mention tag)
        if message.text:
            mention_tag = f"<@personId:{self.me.id}>"
            clean_text = message.text.replace(mention_tag, "").strip()
            return clean_text
            
        return None
# -- End Method process_message

    def _handle_event(self, event: Dict[str, Any]) -> None:
        """
        Dispatches incoming webhook events.
        'event' is the raw JSON dictionary from the Webex API.
        """
        resource: Optional[str] = event.get('resource')
        data: Dict[str, Any] = event.get('data', {})

        if resource == 'messages':
            # Ignore messages sent by the bot itself
            if data.get('personId') == self.me.id: 
                return

            # Fetch the clean text
            clean_text = self.process_message(data['id'])
            if clean_text is None:
                self.logger.debug("Message ignored: Not a DM or Mention.")
                return

            # Create a simple message object for our handlers
            # Using a class or SimpleNamespace here makes the handlers type-safe
            from types import SimpleNamespace
            message = SimpleNamespace(
                roomId=data['roomId'], 
                personId=data['personId'], 
                text=clean_text
            )

            # Match routes
            for regex, handler in self._hears_routes:
                match = regex.search(clean_text)
                if match:
                    handler(self, message, match)
                    break 
        # -- End Resource 'messages'

        elif resource == 'attachmentActions':
            action = self.api.attachment_actions.get(data['id'])
            for callback in self._action_callbacks:
                callback(self, action)
        # -- End Resource 'attachmentActions'
# -- End Method _handle_event
# -- End Class WebexBot

def create_instance_bot(name: str, endpoint: str, **kwargs) -> WebexBot:
    """Factory interface for the Webex driver."""
    token = kwargs.get("token")
    secret = kwargs.get("secret")
    return WebexBot(name, endpoint, token, secret)
# -- End Function create_instance_bot