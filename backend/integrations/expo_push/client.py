"""
Expo Push Notification Service Client.

This service handles communication with Expo Push API for sending push notifications.
Documentation: https://docs.expo.dev/push-notifications/sending-notifications/
"""

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("ledova_backend")


class ExpoPushError(Exception):
    """Custom exception for Expo Push API errors."""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.details = details or {}


class ExpoPushClient:
    """
    Client for sending push notifications via Expo Push API.

    The Expo Push API is a simple, free service that handles sending
    notifications to iOS and Android devices through a unified interface.

    No authentication is required for the Expo Push API.
    """

    EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
    MAX_BATCH_SIZE = 100  # Expo recommends max 100 messages per request

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
                "Content-Type": "application/json",
            }
        )

    def _validate_token(self, token: str) -> bool:
        """
        Validate that a token follows the Expo push token format.

        Args:
            token: The push token to validate

        Returns:
            True if the token is valid, False otherwise
        """
        return token.startswith("ExponentPushToken[") and token.endswith("]")

    def send_batch(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Send multiple notifications in a batch.

        Each message should have the format:
        {
            "to": "ExponentPushToken[xxx]",
            "title": "Title",
            "body": "Body text",
            "data": {},  # Optional
            "badge": 1,  # Optional
            "sound": "default",  # Optional
            "priority": "default",  # Optional
        }

        Args:
            messages: List of message dictionaries

        Returns:
            List of responses from Expo Push API

        Raises:
            ExpoPushError: If the batch fails to send
        """
        if not messages:
            return []

        # Validate all tokens
        for msg in messages:
            if not self._validate_token(msg.get("to", "")):
                raise ExpoPushError(f"Invalid Expo push token format: {msg.get('to')}")

        # Split into batches if needed
        results = []
        for i in range(0, len(messages), self.MAX_BATCH_SIZE):
            batch = messages[i : i + self.MAX_BATCH_SIZE]
            batch_results = self._send_request(batch)
            results.extend(batch_results)

        return results

    def _send_request(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Send request to Expo Push API.

        Args:
            messages: List of message dictionaries

        Returns:
            List of ticket responses from Expo

        Raises:
            ExpoPushError: If the request fails
        """
        try:
            logger.info(f"[EXPO_PUSH] Sending {len(messages)} notification(s)")

            response = self.session.post(
                self.EXPO_PUSH_URL,
                json=messages,
                timeout=30,
            )

            if not response.ok:
                logger.error(f"[EXPO_PUSH] API Error: {response.status_code} - {response.text}")
                raise ExpoPushError(
                    f"Expo Push API error: {response.status_code}",
                    {"status_code": response.status_code, "response": response.text},
                )

            response_data = response.json()
            tickets = response_data.get("data", [])

            # Log any errors in the tickets
            for i, ticket in enumerate(tickets):
                if ticket.get("status") == "error":
                    logger.warning(
                        f"[EXPO_PUSH] Notification {i} failed: " f"{ticket.get('message')} - {ticket.get('details')}"
                    )
                else:
                    logger.debug(f"[EXPO_PUSH] Notification {i} sent: {ticket.get('id')}")

            return tickets

        except requests.RequestException as e:
            logger.error(f"[EXPO_PUSH] Request failed: {e}")
            raise ExpoPushError(f"Failed to send push notification: {e}")
