from django.db import connections

from .aliases import current_alias

PRINCIPAL_SETTING = "app.user_id"


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
