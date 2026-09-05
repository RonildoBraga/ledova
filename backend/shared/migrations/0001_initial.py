import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Country",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(blank=True, max_length=100, null=True)),
                ("code", models.CharField(blank=True, max_length=3, null=True)),
                ("dial_code", models.CharField(blank=True, max_length=10, null=True)),
                ("is_available", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name_plural": "Countries",
            },
        ),
    ]
