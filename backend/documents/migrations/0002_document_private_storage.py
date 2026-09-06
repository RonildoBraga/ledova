from django.db import migrations, models

import documents.models.document
import shared.storage
from shared.utils.migrations import move_uploads, widen_char_column

MODEL = ("documents", "Document", "file")
FILE_MAX_LENGTH = 255


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            move_uploads(*MODEL, to_private=True),
            move_uploads(*MODEL, to_private=False),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="document",
                    name="file",
                    field=models.FileField(
                        max_length=FILE_MAX_LENGTH,
                        storage=shared.storage.private_storage,
                        upload_to=documents.models.document.document_upload_path,
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            widen_char_column(*MODEL, max_length=FILE_MAX_LENGTH),
            migrations.RunPython.noop,
        ),
    ]
