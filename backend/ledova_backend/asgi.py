import os

from django.conf import settings
from django.core.asgi import get_asgi_application

from ledova_backend.environment import (
    assert_media_storage_is_servable,
    assert_requests_are_served_on_the_scoped_connection,
)
from shared.db import APP_ALIAS

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings")

application = get_asgi_application()

assert_media_storage_is_servable(debug=settings.DEBUG, storage_backend=settings.STORAGE_BACKEND)
assert_requests_are_served_on_the_scoped_connection(ambient_alias=settings.RLS_AMBIENT_ALIAS, scoped_alias=APP_ALIAS)
