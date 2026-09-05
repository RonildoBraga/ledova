import tempfile

from . import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGE_BACKEND = "local"
MEDIA_ROOT = tempfile.mkdtemp(prefix="ledova-test-media-")


class _DisableMigrations(dict):
    def __contains__(self, _item):
        return True

    def __getitem__(self, _item):
        return None


MIGRATION_MODULES = _DisableMigrations()
