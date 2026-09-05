import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class ExpoPushError(Exception):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.details = details or {}


class ExpoPushClient:

    EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
    MAX_BATCH_SIZE = 100

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
        return token.startswith("ExponentPushToken[") and token.endswith("]")

    def send_batch(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not messages:
            return []

        for msg in messages:
            if not self._validate_token(msg.get("to", "")):
                raise ExpoPushError(f"Invalid Expo push token format: {msg.get('to')}")

        results = []
        for i in range(0, len(messages), self.MAX_BATCH_SIZE):
            batch = messages[i : i + self.MAX_BATCH_SIZE]
            batch_results = self._send_request(batch)
            results.extend(batch_results)

        return results

    def _send_request(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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

            for i, ticket in enumerate(tickets):
                if ticket.get("status") == "error":
                    logger.warning(
                        f"[EXPO_PUSH] Notification {i} failed: {ticket.get('message')} - {ticket.get('details')}"
                    )
                else:
                    logger.debug(f"[EXPO_PUSH] Notification {i} sent: {ticket.get('id')}")

            return tickets

        except requests.RequestException as e:
            logger.error(f"[EXPO_PUSH] Request failed: {e}")
            raise ExpoPushError(f"Failed to send push notification: {e}")
