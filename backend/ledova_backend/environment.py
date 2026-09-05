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


def assert_media_storage_is_servable(*, debug: bool, storage_backend: str) -> None:
    if debug or storage_backend != "local":
        return
    raise ImproperlyConfigured(
        "STORAGE_BACKEND=local is only servable while DEBUG is true: the /media/ route is registered by "
        "django.conf.urls.static, which returns no patterns when DEBUG is false, so every uploaded document "
        "answers 404. Set STORAGE_BACKEND to s3 or gcs for any deployment that runs with DEBUG=false."
    )
