import atexit
import shutil
import tempfile

from . import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGE_BACKEND = "local"
MEDIA_ROOT = tempfile.mkdtemp(prefix="ledova-test-media-")
PRIVATE_MEDIA_ROOT = tempfile.mkdtemp(prefix="ledova-test-private-media-")

atexit.register(shutil.rmtree, MEDIA_ROOT, ignore_errors=True)
atexit.register(shutil.rmtree, PRIVATE_MEDIA_ROOT, ignore_errors=True)


class _DisableMigrations(dict):
    def __contains__(self, _item):
        return True

    def __getitem__(self, _item):
        return None


MIGRATION_MODULES = _DisableMigrations()

RLS_AMBIENT_ALIAS = "default"
