from tokens.events import TRADING_EVENT_TYPES

TRADING_EVENTS_PATH = "/api/v1/trading/events/stream/"

CONNECTED_EVENT = "connected"

STREAM_DESCRIPTION = (
    "Server-sent events for one deployed share class. The connection opens with a `connected` event "
    'carrying `{"status": "ok"}`, then emits one named event per trading change with an empty data '
    "object: the event name is the whole signal, and the client refetches on it. A comment line "
    "`: heartbeat` is sent every 30 seconds so an idle connection is not closed by an intermediary. "
    "The stream is scoped by users.services.eligibility: an ineligible caller and a phantom token are "
    "the same 404."
)

NOT_A_DRF_VIEW = (
    "This route is a plain async Django function view returning StreamingHttpResponse, so the generator "
    "cannot see it and neither schema gate can classify it. The path is injected here so the contract is "
    "in the schema the type-drift gate diffs against."
)


def event_names():
    return [CONNECTED_EVENT, *sorted(TRADING_EVENT_TYPES)]


def _stream_response():
    return {
        "description": "The event stream.",
        "content": {
            "text/event-stream": {
                "schema": {
                    "type": "string",
                    "description": STREAM_DESCRIPTION,
                    "x-sse-events": event_names(),
                }
            }
        },
    }


def _text_response(description):
    return {"description": description, "content": {"text/plain": {"schema": {"type": "string"}}}}


def document_trading_events_stream(result, generator, request, public):
    result.setdefault("paths", {})[TRADING_EVENTS_PATH] = {
        "get": {
            "operationId": "trading_events_stream_retrieve",
            "description": NOT_A_DRF_VIEW,
            "summary": "Stream trading events for one share class",
            "tags": ["trading"],
            "parameters": [
                {
                    "in": "query",
                    "name": "token",
                    "required": False,
                    "description": "Share class uuid. Omitted or unknown answers 404.",
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": _stream_response(),
                "401": _text_response("No authenticated caller."),
                "404": _text_response("No streamable share class for this caller."),
            },
        }
    }
    return result
