"""Twilio SMS client."""

import logging

from django.conf import settings
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


class TwilioIntegration:
    """Client for sending SMS messages via Twilio."""

    def __init__(self):
        """Initialize the Twilio client with configuration from Django settings."""
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_phone = settings.TWILIO_FROM_PHONE

        # Initialize client at instance level
        self.client = None
        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            logger.warning(
                f"{LoggingContext.INTEGRATIONS} Twilio credentials not configured. SMS functionality will not work."
            )

    def send_sms(self, to_number, message):
        """
        Send SMS message using Twilio

        Args:
            to_number (str): The recipient's phone number
            message (str): The message content

        Returns:
            dict: Response from Twilio API or error info
        """
        if not self.client:
            logger.error(f"{LoggingContext.INTEGRATIONS} Twilio client not initialized. Cannot send SMS.")
            return {"success": False, "error": "Twilio client not initialized"}

        if not self.from_phone:
            logger.error(f"{LoggingContext.INTEGRATIONS} Twilio sender phone number not configured")
            return {"success": False, "error": "Sender phone number not configured"}

        try:
            sms_message = self.client.messages.create(body=message, from_=self.from_phone, to=to_number)
            logger.info(f"{LoggingContext.INTEGRATIONS} SMS sent to {to_number}, Twilio SID: {sms_message.sid}")
            return {"success": True, "sid": sms_message.sid}
        except TwilioRestException as e:
            logger.error(f"{LoggingContext.INTEGRATIONS} Failed to send SMS: {str(e)}")
            return {"success": False, "error": str(e)}


# Singleton instance for use throughout the application
twilio_integration = TwilioIntegration()
