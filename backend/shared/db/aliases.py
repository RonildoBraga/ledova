import threading
from contextlib import contextmanager

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

APP_ALIAS = "app"
OPERATOR_ALIAS = "operator"
MIGRATE_ALIAS = "default"

_state = threading.local()


def current_alias() -> str:
    return getattr(_state, "alias", settings.RLS_AMBIENT_ALIAS)


def configured(alias: str) -> str:
    if settings.RLS_AMBIENT_ALIAS == MIGRATE_ALIAS:
        return MIGRATE_ALIAS
    if alias not in settings.DATABASES:
        raise ImproperlyConfigured(
            f"DATABASES has no {alias!r} alias, and RLS_AMBIENT_ALIAS is {settings.RLS_AMBIENT_ALIAS!r}, "
            "so this process expects the roles to be separate connections and they are not configured."
        )
    return alias


@contextmanager
def _using(alias: str):
    previous = getattr(_state, "alias", None)
    _state.alias = alias
    try:
        yield
    finally:
        if previous is None:
            del _state.alias
        else:
            _state.alias = previous


def use_operator():
    return _using(configured(OPERATOR_ALIAS))


def use_app():
    return _using(configured(APP_ALIAS))


def use_migrate():
    return _using(configured(MIGRATE_ALIAS))


def select_operator() -> None:
    _state.alias = configured(OPERATOR_ALIAS)


def clear_alias() -> None:
    _state.__dict__.pop("alias", None)
