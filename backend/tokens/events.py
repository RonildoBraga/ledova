import json
import logging

import redis
from django.conf import settings

from shared.db import on_commit

logger = logging.getLogger(__name__)

CONNECTED_EVENT = "connected"
TRADING_EVENTS_CHANNEL = "trading:events"
TRADING_EVENT_TYPES = frozenset(
    {
        "order_created",
        "order_cancelled",
        "order_modified",
        "order_matched",
        "swap_signed",
        "swap_completed",
        "swap_failed",
        "swap_expired",
    }
)

_redis_client = None


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.REDIS_URL)
    return _redis_client


def publish_trading_event(event_type: str, token_uuid: str):
    if event_type not in TRADING_EVENT_TYPES:
        logger.error("Refusing unsupported trading event type")
        return

    payload = {
        "event": event_type,
        "token": str(token_uuid),
    }
    on_commit(lambda: _publish(event_type, payload))


def _publish(event_type: str, payload: dict) -> None:
    try:
        client = _get_redis_client()
        client.publish(TRADING_EVENTS_CHANNEL, json.dumps(payload))
    except Exception:
        logger.exception("Failed to publish trading event: %s", event_type)
