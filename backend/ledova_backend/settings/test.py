import atexit
import shutil
import tempfile
from copy import deepcopy

from . import *  # noqa: F401,F403
from .database import DATABASES as POSTGRES_DATABASES

DATABASES = deepcopy(POSTGRES_DATABASES)
DATABASES["default"]["CONN_MAX_AGE"] = 0
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGE_BACKEND = "local"
MEDIA_ROOT = tempfile.mkdtemp(prefix="ledova-test-media-")
PRIVATE_MEDIA_ROOT = tempfile.mkdtemp(prefix="ledova-test-private-media-")

atexit.register(shutil.rmtree, MEDIA_ROOT, ignore_errors=True)
atexit.register(shutil.rmtree, PRIVATE_MEDIA_ROOT, ignore_errors=True)

RLS_AMBIENT_ALIAS = "default"
