import threading
from contextlib import contextmanager

from django.conf import settings
from django.db import connections

from .aliases import current_alias

PRINCIPAL_SETTING = "app.user_id"

_role = threading.local()


def _postgres(alias):
    connection = connections[alias or current_alias()]
    return connection if connection.vendor == "postgresql" else None


def set_principal(user_id: int, alias: str | None = None) -> None:
    connection = _postgres(alias)
    if connection is None:
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(user_id)])


def reset_principal(alias: str | None = None) -> None:
    connection = _postgres(alias)
    if connection is None or connection.connection is None:
        return
    with connection.cursor() as cursor:
        cursor.execute(f"RESET {PRINCIPAL_SETTING}")


def principal_of(alias: str | None = None):
    connection = _postgres(alias)
    if connection is None:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [PRINCIPAL_SETTING])
        return cursor.fetchone()[0]


def the_app_role_is_taken() -> bool:
    return getattr(_role, "taken", False)


def take_the_app_role(alias: str | None = None) -> None:
    if not getattr(settings, "RLS_ROLE_PER_REQUEST", False):
        return
    connection = _postgres(alias)
    if connection is None:
        return
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{settings.RLS_ROLES["app"]}"')
    _role.taken = True


def give_the_role_back(alias: str | None = None) -> None:
    if not getattr(settings, "RLS_ROLE_PER_REQUEST", False):
        return
    _role.taken = False
    connection = _postgres(alias)
    if connection is None or connection.connection is None:
        return
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")


@contextmanager
def the_owner_for_a_moment():
    if not the_app_role_is_taken():
        yield
        return
    give_the_role_back()
    try:
        yield
    finally:
        take_the_app_role()
