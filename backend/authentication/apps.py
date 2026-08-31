from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authentication"
    verbose_name = "1 - Authentication"

    def ready(self):
        """Import signals when Django is ready to ensure they're connected"""
