import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FeatureFlag",
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
                (
                    "name",
                    models.CharField(
                        help_text="Unique flag identifier (e.g. 'enable_dark_mode')", max_length=100, unique=True
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, help_text="Human-readable description of what this flag controls"),
                ),
                ("enabled", models.BooleanField(default=False, help_text="Whether this flag is currently active")),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("all", "All Platforms"),
                            ("ios", "iOS"),
                            ("android", "Android"),
                            ("web", "Web"),
                            ("mobile", "Mobile (iOS + Android)"),
                        ],
                        default="all",
                        help_text="Which platform(s) this flag applies to",
                        max_length=10,
                    ),
                ),
                (
                    "min_app_version",
                    models.CharField(
                        blank=True,
                        help_text="Minimum app version required (e.g. '1.2.0'). Leave blank to apply to all versions.",
                        max_length=20,
                    ),
                ),
            ],
            options={
                "verbose_name": "Feature Flag",
                "verbose_name_plural": "Feature Flags",
                "db_table": "feature_flags",
                "ordering": ["name"],
            },
        ),
    ]
