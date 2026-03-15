# bots/webex_bot.py
# Thaum Engine v1.0.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import logging
from __future__ import annotations
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from thaum.identity import get_person_by_id,cache_person
from thaum.types import ThaumPerson, ResolvedSecret
from webexpythonsdk import WebexAPI
from bots.base import BaseBot, MessageContext, BaseBotConfig
from log_setup import log_debug_blob


class WebexBot(BaseBot):
    """Concrete driver for Webex."""

    plugin_name: str = 'webex'

    def __init__(self, config: 'WebexBotConfig'):
        super().__init__(config)
        self.logger = logging.getLogger(f"bot.{config.name}")
        self.api = WebexAPI(access_token=config.token.get_secret_value())
        self.me = self.api.people.me()
        self.hmac_secret = (
            None if config.hmac_secret is None
            else config.hmac_secret.get_secret_value()
        )
        
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
            if m.platform_ids[self.plugin_name]:
                key="personId"
                v=m.platform_ids[self.plugin_name]
            else:
                key="personEmail"
                v=m.email
            
            try:
                self.api.memberships.create(roomId=room_id, **{key: v})
            except Exception as e:
                self.logger.error(f"Failed to add {m} to {room_id}: {e}")
    # -- End Method add_members

    def delete_room(self, room_id: str, person: Optional[ThaumPerson] = None) -> None:
        """Implodes the room ONLY if bot is the creator."""
        display_name = person.for_display() if person else "An unknown user"
        
        try:
            room = self.api.rooms.get(room_id)
            
            if room.creatorId != self.me.id:
                self.logger.warning(f"Unauthorized attempt to delete room '{room.title}' by {display_name}")
                self.say(room_id, f"Access Denied: {self.name} did not create room '{room.title}'")
                return # Stop here, don't crash the server
                
            self.api.rooms.delete(room_id)
            self.logger.verbose(f"Room {room_id} deleted by {display_name}.")
            
        except Exception as e:
            # Here is the only place you actually need an exception handler
            self.logger.error(f"Catastrophic failure deleting {room_id}: {e}")
            self.say(room_id, "Critical failure during room deletion.")

    # -- End Method delete_room


    def _get_person_from_api(self, person_id: str) -> ThaumPerson:
        """
        Fetches a person from the Webex API and returns a ThaumPerson.
        """
        try:
            # 1. Fetch the person object
            person = self.api.people.get(person_id)
            
            # 2. Extract the canonical email (take the first one if multiple exist)
            email = person.emails[0] if person.emails else None
            
            # 3. Handle cases where API might not return an email (rare but possible)
            if not email:
                self.logger.warning(f"Webex person {person_id} has no email. Using ID as fallback.")
                email = f"{person_id}@{self.plugin_name}"
                
            # 4. Map to ThaumPerson
            return ThaumPerson(
                email=email,
                display_name=person.displayName,
                platform_ids={self.plugin_name: person_id},
                source_plugin=self.plugin_name # e.g., 'webex_bot'
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch person {person_id} from Webex: {e}")
            # Return a 'placeholder' person so the system doesn't crash
            return None
    # -- End Method get_person_from_api

    def get_person(self,person_id) -> ThaumPerson:
        p=get_person_by_id(self.plugin_name,person_id)
        if not p:
            p=self._get_person_from_api(person_id)
            if p:
                p=cache_person(p)
            else:
                p=ThaumPerson(email=f"{person_id}@{self.plugin_name}",platform_ids={self.plugin_name: person_id})
        return p
    
    def validate_signature(self, payload_body: bytes, signature: Optional[str]) -> bool:
        if self.secret is None: return True
        if not signature: return False
        
        import hmac, hashlib
        hashed = hmac.new(self.secret.encode(), payload_body, hashlib.sha1)
        return hmac.compare_digest(hashed.hexdigest(), signature)
    # -- End Method validate_signature

    def _process_message(self, message_id: str) -> Optional[str]:
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

    def handle_event(self, event: Dict[str, Any]) -> None:
        """
        Dispatches incoming webhook events.
        'event' is the raw JSON dictionary from the Webex API.
        """
        self.logger.spam("handle_event:")
        log_debug_blob(self.logger,data,logging.SPAM)
        resource: Optional[str] = event.get('resource')
        data: Dict[str, Any] = event.get('data', {})

        if resource == 'messages':
            # Ignore messages sent by the bot itself
            if data.get('personId') == self.me.id: 
                return

            # Fetch the clean text
            clean_text = self._process_message(data['id'])
            if clean_text is None:
                self.logger.debug("Message ignored: Not a DM or Mention.")
                return

            person=self.get_person(data['personId'])
            message=MessageContext(
                room_id=data['roomId'],
                person=person,
                message=clean_text,
                message_id=data['id'],
                raw_event=event
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

class WebexBotConfig(BaseBotConfig):
    token: ResolvedSecret
    hmac_secret: ResolvedSecret

def create_instance_bot(name: str, endpoint: str, **kwargs) -> WebexBot:
    """Factory interface for the Webex driver."""
    token = kwargs.get("token")
    secret = kwargs.get("secret")
    return WebexBot(name, endpoint, token, secret)
# -- End Function create_instance_bot