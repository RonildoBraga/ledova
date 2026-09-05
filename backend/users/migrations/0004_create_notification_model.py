import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_alter_userpreferences_preferred_onramp_provider"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
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
                    "title",
                    models.CharField(help_text="Notification title", max_length=255),
                ),
                (
                    "body",
                    models.TextField(help_text="Notification body text"),
                ),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("transaction", "Transaction"),
                            ("price", "Price"),
                            ("marketing", "Marketing"),
                            ("general", "General"),
                            ("system", "System"),
                        ],
                        default="general",
                        help_text="Category of the notification",
                        max_length=20,
                    ),
                ),
                (
                    "data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional structured data for the notification",
                    ),
                ),
                (
                    "is_read",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the notification has been read",
                    ),
                ),
                (
                    "read_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the notification was read",
                        null=True,
                    ),
                ),
                (
                    "is_archived",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the notification has been archived",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="The user this notification belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Notification",
                "verbose_name_plural": "Notifications",
                "db_table": "notifications",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["user", "-created_at"],
                name="idx_notification_user_created",
            ),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["user", "is_read"],
                name="idx_notification_user_read",
            ),
        ),
    ]
