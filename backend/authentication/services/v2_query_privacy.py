from django.db import connections

_QUERY_RECORDING_ERROR = "V2 challenge service unavailable."


def _require_unrecorded_v2_connection(*, using):
    selected = None
    try:
        selected = connections[using]
        recording_disabled = selected.queries_logged is False
    except Exception:
        recording_disabled = False

    if not recording_disabled:
        raise RuntimeError(_QUERY_RECORDING_ERROR) from None

    return selected
