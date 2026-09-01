import asyncio
import json
import logging
from types import SimpleNamespace
from uuid import UUID

import redis.asyncio as aioredis
from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse

from authentication.classes import HybridJWTAuthentication
from tokens.events import TRADING_EVENT_TYPES, TRADING_EVENTS_CHANNEL
from tokens.models import ShareToken

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30


def _authenticate_sync(request):
    """Use the normal JWT lifecycle, retaining the tracked query fallback."""
    authentication = HybridJWTAuthentication()
    result = authentication.authenticate(request)
    if result is not None:
        return result[0]

    try:
        user = request.user
        if user.is_authenticated and user.is_active:
            return user
    except Exception:
        pass

    # Mobile's URL token transport remains until GitHub issue #3 is addressed.
    query_token = request.GET.get("auth")
    if query_token:
        query_request = SimpleNamespace(
            COOKIES={},
            META={**request.META, "HTTP_AUTHORIZATION": f"Bearer {query_token}"},
        )
        result = authentication.authenticate(query_request)
        if result is not None:
            return result[0]

    return None


async def _authenticate(request):
    return await sync_to_async(_authenticate_sync, thread_sensitive=True)(request)


def _format_sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _format_public_trading_event(event, token_uuid: str):
    """Return an identifier-free event for the requested public market."""
    if not isinstance(event, dict) or event.get("token") != token_uuid:
        return None

    event_type = event.get("event")
    if event_type not in TRADING_EVENT_TYPES:
        return None

    return _format_sse(event_type, {})


async def _resolve_deployed_token_uuid(raw_token_uuid):
    """Resolve only UUIDs exposed by the deployed-token trading market."""
    try:
        token_uuid = str(UUID(raw_token_uuid))
    except (AttributeError, TypeError, ValueError):
        return None

    if not await ShareToken.objects.deployed().filter(uuid=token_uuid).aexists():
        return None

    return token_uuid


async def _event_stream(token_uuid: str):
    """Async generator that subscribes to Redis and yields SSE-formatted events."""
    client = aioredis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    subscribed = False

    try:
        await pubsub.subscribe(TRADING_EVENTS_CHANNEL)
        subscribed = True
        yield _format_sse("connected", {"status": "ok"})

        last_heartbeat = asyncio.get_event_loop().time()

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if message is None:
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                continue

            if not isinstance(message, dict) or message.get("type") != "message":
                continue

            try:
                event = json.loads(message.get("data"))
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                continue

            public_event = _format_public_trading_event(event, token_uuid)
            if public_event is None:
                continue

            yield public_event

    except asyncio.CancelledError:
        pass
    finally:
        try:
            if subscribed:
                await pubsub.unsubscribe(TRADING_EVENTS_CHANNEL)
        finally:
            try:
                await pubsub.aclose()
            finally:
                await client.aclose()


async def trading_events_stream(request):
    """SSE endpoint for real-time trading updates."""
    user = await _authenticate(request)
    if user is None:
        return HttpResponse("Unauthorized", status=401, content_type="text/plain")

    token_uuid = await _resolve_deployed_token_uuid(request.GET.get("token"))
    if token_uuid is None:
        return HttpResponse("Token not found", status=404, content_type="text/plain")

    response = StreamingHttpResponse(
        _event_stream(token_uuid),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
