import logging

from django.core.files.storage import storages
from django.db import migrations, models

import companies.models.document
import shared.storage

logger = logging.getLogger(__name__)


def _relocate(apps, source_alias, target_alias):
    source = storages[source_alias]
    target = storages[target_alias]
    if type(source) is type(target):
        return

    CompanyDocument = apps.get_model("companies", "CompanyDocument")
    for uuid, name in CompanyDocument.objects.exclude(file="").values_list("uuid", "file"):
        if not name or target.exists(name):
            continue
        if not source.exists(name):
            logger.warning("Company document %s has no file at %s; leaving the row as it stands.", uuid, name)
            continue
        with source.open(name) as handle:
            target.save(name, handle)
        source.delete(name)


def move_files_into_private_storage(apps, schema_editor):
    _relocate(apps, "default", "private")


def move_files_back_into_default_storage(apps, schema_editor):
    _relocate(apps, "private", "default")


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0005_company_is_open_to_investors"),
    ]

    operations = [
        migrations.AlterField(
            model_name="companydocument",
            name="file",
            field=models.FileField(
                blank=True,
                help_text="Uploaded file (preferred), read back through the authenticated route",
                max_length=255,
                null=True,
                storage=shared.storage.private_storage,
                upload_to=companies.models.document.company_document_path,
            ),
        ),
        migrations.RunPython(move_files_into_private_storage, move_files_back_into_default_storage),
    ]
