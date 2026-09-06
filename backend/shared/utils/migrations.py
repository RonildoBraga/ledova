import os
import shutil

from django.conf import settings


def _stored_names(apps, app_label, model_name, field_name):
    model = apps.get_model(app_label, model_name)
    return list(
        model.objects.exclude(**{field_name: ""})
        .exclude(**{f"{field_name}__isnull": True})
        .values_list(field_name, flat=True)
    )


def _relocate(names, source_root, destination_root):
    for name in names:
        source = os.path.join(source_root, name)
        destination = os.path.join(destination_root, name)
        if not os.path.isfile(source) or os.path.exists(destination):
            continue
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)


def move_uploads(app_label, model_name, field_name, to_private):
    def run(apps, schema_editor):
        if getattr(settings, "STORAGE_BACKEND", "") != "local":
            return
        source_root = settings.MEDIA_ROOT if to_private else settings.PRIVATE_MEDIA_ROOT
        destination_root = settings.PRIVATE_MEDIA_ROOT if to_private else settings.MEDIA_ROOT
        _relocate(_stored_names(apps, app_label, model_name, field_name), source_root, destination_root)

    return run


def widen_char_column(app_label, model_name, field_name, max_length):
    def run(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        model = apps.get_model(app_label, model_name)
        table = schema_editor.quote_name(model._meta.db_table)
        column = schema_editor.quote_name(model._meta.get_field(field_name).column)
        schema_editor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar({max_length})")

    return run
