import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blockchain", "0001_initial"),
        ("tokens", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="YieldToken",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                ("symbol", models.CharField(max_length=10, unique=True)),
                ("contract_address", models.CharField(max_length=42, unique=True)),
                ("decimals", models.PositiveSmallIntegerField(default=6)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "nav_per_token",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        help_text="Current NAV per token in USD (e.g., 1.005000)",
                        max_digits=20,
                        null=True,
                    ),
                ),
                (
                    "total_reserve_value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        help_text="Synthetic reference value in USD; not evidence of a real reserve",
                        max_digits=20,
                        null=True,
                    ),
                ),
                (
                    "last_nav_update",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp of last NAV update",
                        null=True,
                    ),
                ),
            ],
            options={
                "verbose_name": "Yield Token",
                "verbose_name_plural": "Yield Tokens",
                "ordering": ["symbol"],
            },
        ),
        migrations.CreateModel(
            name="NAVUpdate",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "old_nav_per_token",
                    models.DecimalField(
                        decimal_places=6,
                        help_text="Previous NAV per token",
                        max_digits=20,
                    ),
                ),
                (
                    "new_nav_per_token",
                    models.DecimalField(
                        decimal_places=6,
                        help_text="New NAV per token",
                        max_digits=20,
                    ),
                ),
                (
                    "total_reserve_value",
                    models.DecimalField(
                        decimal_places=6,
                        help_text="Synthetic reference value at time of update",
                        max_digits=20,
                    ),
                ),
                (
                    "custodian_report_ref",
                    models.CharField(
                        blank=True,
                        help_text="Optional synthetic scenario reference (legacy field name)",
                        max_length=200,
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        help_text="Additional notes about this NAV update",
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        blank=True,
                        help_text="On-chain transaction for this NAV update (if executed on-chain)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="nav_updates",
                        to="blockchain.blockchaintransaction",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        help_text="Staff member who performed this update",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nav_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "yield_token",
                    models.ForeignKey(
                        help_text="The yield token whose NAV was updated",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nav_updates",
                        to="tokens.yieldtoken",
                    ),
                ),
            ],
            options={
                "verbose_name": "NAV Update",
                "verbose_name_plural": "NAV Updates",
                "ordering": ["-created_at"],
            },
        ),
    ]
