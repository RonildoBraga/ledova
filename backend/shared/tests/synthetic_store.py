class _EveryAppUnmigrated(dict):
    def __contains__(self, _item):
        return True

    def __getitem__(self, _item):
        return None


def a_private_store_that_survives_a_kill(settings, path):
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(path)}}
    settings.MIGRATION_MODULES = _EveryAppUnmigrated()
