import os
from collections.abc import Collection

from django.core.exceptions import ImproperlyConfigured


def read_bool(name: str, *, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False

    raise ImproperlyConfigured(f"{name} must be either 'true' or 'false'")


def read_choice(name: str, *, choices: Collection[str], default: str) -> str:
    allowed = frozenset(choice.lower() for choice in choices)
    value = os.environ.get(name, default).strip().lower()
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ImproperlyConfigured(f"{name} must be one of: {allowed_values}")
    return value


def resolve_storage_backend(*, debug: bool) -> str:
    configured_backend = read_choice(
        "STORAGE_BACKEND",
        choices=("local", "s3", "gcs"),
        default="local",
    )
    return "local" if debug else configured_backend
