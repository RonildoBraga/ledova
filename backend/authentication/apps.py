from importlib import import_module

from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authentication"
    verbose_name = "1 - Authentication"

    def ready(self):
        import_module("authentication.schema")
