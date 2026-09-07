from django.apps import AppConfig
from django.db.models.signals import post_delete


class SharedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shared"
    verbose_name = "Shared"

    def ready(self):
        from shared.storage import delete_file_when_the_row_is_gone, swept_file_fields

        for model, field_name in swept_file_fields():
            post_delete.connect(
                delete_file_when_the_row_is_gone(field_name),
                sender=model,
                dispatch_uid=f"shared.storage.sweep:{model._meta.label}.{field_name}",
                weak=False,
            )
