import asyncio
import json
import logging

import redis.asyncio as aioredis
from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework_simplejwt.tokens import AccessToken

from tokens.events import TRADING_EVENTS_CHANNEL

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30


async def _authenticate(request):
    """Authenticate via session (dashboard cookies) or JWT query param (mobile)."""
    # Try session-based auth (dashboard) using Django's async user accessor
    try:
        user = await request.auser()
        if user.is_authenticated:
            return user
    except Exception:
        pass

    # Try JWT from query param (mobile)
    jwt_token = request.GET.get("auth")
    if jwt_token:
        try:
            validated = AccessToken(jwt_token)
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user = await User.objects.aget(id=validated["user_id"])
            return user
        except Exception:
            return None

    return None


def _format_sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _event_stream(token_uuid: str):
    """Async generator that subscribes to Redis and yields SSE-formatted events."""
    client = aioredis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe(TRADING_EVENTS_CHANNEL)

    try:
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

            if message["type"] != "message":
                continue

            try:
                event = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue

            if event.get("token") != token_uuid:
                continue

            yield _format_sse(event["event"], event.get("data", {}))

    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(TRADING_EVENTS_CHANNEL)
        await pubsub.aclose()
        await client.aclose()


async def trading_events_stream(request):
    """SSE endpoint for real-time trading updates."""
    user = await _authenticate(request)
    if user is None:
        return StreamingHttpResponse("Unauthorized", status=401, content_type="text/plain")

    token_uuid = request.GET.get("token")
    if not token_uuid:
        return StreamingHttpResponse("Missing token parameter", status=400, content_type="text/plain")

    response = StreamingHttpResponse(
        _event_stream(token_uuid),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
