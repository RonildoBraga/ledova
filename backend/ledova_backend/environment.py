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


def assert_requests_are_served_on_the_scoped_connection(*, ambient_alias: str, scoped_alias: str) -> None:
    if ambient_alias == scoped_alias:
        return
    raise ImproperlyConfigured(
        f"This process serves requests and RLS_AMBIENT_ALIAS is {ambient_alias!r}, so every query it runs "
        f"would take the {ambient_alias!r} connection instead of {scoped_alias!r}. manage.py sets that "
        "variable to the operator alias for command-line work, and a server started through it - or any "
        "entrypoint that inherits an operator environment - would serve the API with row-level security "
        "bypassed and nothing in the database to notice."
    )
