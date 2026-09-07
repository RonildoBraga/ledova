from django.core.management.commands.migrate import Command as DjangoMigrate

from shared.db import use_migrate


class Command(DjangoMigrate):

    def handle(self, *args, **options):
        with use_migrate():
            return super().handle(*args, **options)
