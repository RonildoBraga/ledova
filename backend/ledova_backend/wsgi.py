import os

from django.conf import settings
from django.core.wsgi import get_wsgi_application

from ledova_backend.environment import assert_media_storage_is_servable

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings")

application = get_wsgi_application()

assert_media_storage_is_servable(debug=settings.DEBUG, storage_backend=settings.STORAGE_BACKEND)
