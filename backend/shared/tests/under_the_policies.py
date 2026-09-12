from contextlib import contextmanager

from django.conf import settings
from django.db import connection

from shared.db.principal import PRINCIPAL_SETTING


def _principal(value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, value])


@contextmanager
def only_what_the_policies_admit_to(user):
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{settings.RLS_ROLES["app"]}"')
    _principal(str(user.pk) if user is not None and user.is_authenticated else "")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
        _principal(None)


def what_the_policies_admit_to(user, model):
    with only_what_the_policies_admit_to(user):
        admitted = list(model._default_manager.values_list("pk", flat=True))
    return model._default_manager.filter(pk__in=admitted)
