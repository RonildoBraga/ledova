from contextlib import contextmanager

from django.conf import settings
from django.db import connections

from shared.db import APP_ALIAS, MIGRATE_ALIAS, OPERATOR_ALIAS, current_alias, set_principal, use_operator

EVERY_ALIAS = {MIGRATE_ALIAS, APP_ALIAS, OPERATOR_ALIAS}


def aliases_this_deployment_has() -> set[str]:
    return {alias for alias in EVERY_ALIAS if alias in settings.DATABASES}


class RunsOnTheScopedConnection:

    databases = EVERY_ALIAS

    @contextmanager
    def as_an_operator_would(self):
        with use_operator():
            yield

    def the_principal_the_middleware_would_set(self, user) -> None:
        set_principal(user.pk, current_alias())

    def signed_in_as(self, user):
        self.client.force_authenticate(user=user)
        self.the_principal_the_middleware_would_set(user)
        return user

    def no_principal_is_set(self) -> None:
        connection = connections[current_alias()]
        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, NULL, false)", ["app.user_id"])
