from .aliases import APP_ALIAS, MIGRATE_ALIAS, current_alias


class LedovaRouter:

    def db_for_read(self, model, **hints):
        return current_alias()

    def db_for_write(self, model, **hints):
        return current_alias()

    def allow_relation(self, first, second, **hints):
        return True

    def allow_migrate(self, db, app_label, **hints):
        return db == MIGRATE_ALIAS


__all__ = ["APP_ALIAS", "LedovaRouter"]
