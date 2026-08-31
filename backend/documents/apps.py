from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"
    verbose_name = "8 - Documents"

    def ready(self):
        # Wire the internal-assistant payslip-upload signal handler.
        from documents import signals  # noqa: F401
