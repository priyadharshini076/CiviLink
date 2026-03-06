"""
Twilio Webhook Handler
Handles incoming WhatsApp messages via Twilio and sends responses
"""

import logging
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from core.assistant import CiviLinkAssistant
from privacy.consent_manager import ConsentManager

load_dotenv()

@dataclass
class WhatsAppMessage:
    from_number: str
    message_id: str
    message_type: str
    content: str
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class TwilioWebhookHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER")
        
        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None
            self.logger.warning("Twilio credentials not fully configured")

    def process_message(self, form_data: Dict[str, Any], 
                       assistant: CiviLinkAssistant, 
                       consent_manager: ConsentManager) -> str:
        """Process incoming Twilio WhatsApp message and return TwiML"""
        try:
            # Extract message from Twilio form data
            message = self._extract_message(form_data)
            if not message:
                return str(MessagingResponse())
            
            self.logger.info(f"Processing Twilio message from {message.from_number}")
            
            # Process based on message type
            if message.message_type == "text":
                result = assistant.process_message(message.from_number, message.content, "text")
            elif message.message_type == "audio":
                # Twilio provides media URL in MediaUrl0
                media_url = form_data.get('MediaUrl0')
                result = assistant.process_message(message.from_number, media_url, "voice_url")
            else:
                result = {"response": "I currently support text and voice messages."}

            # Create TwiML response
            twiml = MessagingResponse()
            twiml.message(result.get("response", "I'm sorry, I couldn't process that."))
            return str(twiml)
            
        except Exception as e:
            self.logger.exception(f"Twilio processing error: {str(e)}")
            twiml = MessagingResponse()
            twiml.message("I'm having some technical trouble. Please try again later.")
            return str(twiml)

    def _extract_message(self, data: Dict[str, Any]) -> Optional[WhatsAppMessage]:
        """Extract message info from Twilio POST data"""
        from_number = data.get('From', '')
        body = data.get('Body', '')
        msg_id = data.get('MessageSid', '')
        num_media = int(data.get('NumMedia', 0))
        
        msg_type = "text"
        if num_media > 0:
            media_content_type = data.get('MediaContentType0', '')
            if 'audio' in media_content_type:
                msg_type = "audio"
            elif 'image' in media_content_type:
                msg_type = "image"
            elif 'pdf' in media_content_type:
                msg_type = "document"

        return WhatsAppMessage(
            from_number=from_number,
            message_id=msg_id,
            message_type=msg_type,
            content=body
        )

    def send_direct_message(self, to_number: str, message_text: str):
        """Send proactive message (outside of webhook response)"""
        if not self.client:
            self.logger.error("Twilio client not initialized")
            return
        
        try:
            self.client.messages.create(
                from_=f"whatsapp:{self.whatsapp_number}",
                body=message_text,
                to=to_number
            )
        except Exception as e:
            self.logger.error(f"Failed to send direct Twilio message: {str(e)}")
