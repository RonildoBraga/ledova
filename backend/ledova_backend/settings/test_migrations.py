from . import test as _test

for _name in dir(_test):
    if _name.isupper():
        globals()[_name] = getattr(_test, _name)


class _AuthenticationMigrationsOnly(dict):
    enabled = {"auth", "authentication", "contenttypes"}

    def __contains__(self, item):
        return item not in self.enabled

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _AuthenticationMigrationsOnly()
