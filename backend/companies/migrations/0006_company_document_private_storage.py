import os
import shutil

from django.conf import settings
from django.db import migrations, models

import companies.models.document
import shared.storage


def move_company_documents_to_private_media(apps, schema_editor):
    if getattr(settings, "STORAGE_BACKEND", "") != "local":
        return

    CompanyDocument = apps.get_model("companies", "CompanyDocument")
    names = CompanyDocument.objects.exclude(file="").exclude(file=None).values_list("file", flat=True)

    for name in names:
        source = os.path.join(settings.MEDIA_ROOT, name)
        destination = os.path.join(settings.PRIVATE_MEDIA_ROOT, name)
        if not os.path.isfile(source) or os.path.exists(destination):
            continue
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)


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
                help_text="Uploaded file (preferred)",
                max_length=255,
                null=True,
                storage=shared.storage.private_storage,
                upload_to=companies.models.document.company_document_path,
            ),
        ),
        migrations.RunPython(
            move_company_documents_to_private_media,
            migrations.RunPython.noop,
        ),
    ]
