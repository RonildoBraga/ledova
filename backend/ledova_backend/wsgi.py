import os

from django.conf import settings
from django.core.wsgi import get_wsgi_application

from ledova_backend.environment import (
    assert_media_storage_is_servable,
    assert_requests_are_served_on_the_scoped_connection,
)
from shared.db import APP_ALIAS
from shared.upload_gateway import BoundedUploadWSGI

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings")

application = BoundedUploadWSGI(get_wsgi_application())

assert_media_storage_is_servable(debug=settings.DEBUG, storage_backend=settings.STORAGE_BACKEND)
assert_requests_are_served_on_the_scoped_connection(ambient_alias=settings.RLS_AMBIENT_ALIAS, scoped_alias=APP_ALIAS)
