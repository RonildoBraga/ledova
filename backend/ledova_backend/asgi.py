import os

from django.conf import settings
from django.core.asgi import get_asgi_application

from ledova_backend.environment import assert_media_storage_is_servable

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings")

application = get_asgi_application()

assert_media_storage_is_servable(debug=settings.DEBUG, storage_backend=settings.STORAGE_BACKEND)
