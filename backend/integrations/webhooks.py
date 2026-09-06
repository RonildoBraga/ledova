from datetime import datetime, timezone
from typing import Optional

from django.utils import timezone as django_timezone

WEBHOOK_MAX_AGE_SECONDS = 300

TIMESTAMP_KEYS = ("createdAtMs", "createdAt", "created_at", "timestamp")

_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
)


def _parse(value) -> Optional[datetime]:
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip().replace("Z", "+0000")
    for fmt in _FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def signed_timestamp(payload) -> Optional[datetime]:
    if not isinstance(payload, dict):
        return None
    for key in TIMESTAMP_KEYS:
        if key in payload:
            parsed = _parse(payload[key])
            if parsed is not None:
                return parsed
    return None


def is_stale(payload, max_age_seconds: int = WEBHOOK_MAX_AGE_SECONDS) -> bool:
    sent_at = signed_timestamp(payload)
    if sent_at is None:
        return False
    return abs((django_timezone.now() - sent_at).total_seconds()) > max_age_seconds
