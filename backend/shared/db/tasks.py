from contextlib import contextmanager

from .aliases import use_app, use_operator
from .principal import reset_principal, set_principal


@contextmanager
def acting_for(principal_id):
    if principal_id is None:
        with use_operator():
            yield
        return

    with use_app():
        set_principal(int(principal_id))
        try:
            yield
        finally:
            reset_principal()
