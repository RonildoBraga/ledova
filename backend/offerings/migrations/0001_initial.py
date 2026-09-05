import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("assets", "0012_audy_base_deployment"),
        ("companies", "0005_company_is_open_to_investors"),
        ("tokens", "0016_drop_stablecoin"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Offering",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("submitted", "Submitted for Review"),
                            ("under_review", "Under Review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("closed", "Closed"),
                            ("withdrawn", "Withdrawn"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                (
                    "exemption",
                    models.CharField(
                        choices=[
                            ("s708_8_minimum_amount", "Minimum amount of AUD 500,000 (s708(8)(a))"),
                            ("s708_8_net_assets", "Net assets certified by a qualified accountant (s708(8)(c))"),
                            ("s708_8_gross_income", "Gross income certified by a qualified accountant (s708(8)(c))"),
                            ("s708_11_professional", "Professional investor (s708(11))"),
                            ("s761g_wholesale_client", "Wholesale client (s761G)"),
                        ],
                        max_length=30,
                    ),
                ),
                ("price_per_share", models.DecimalField(decimal_places=2, max_digits=18)),
                (
                    "price_currency",
                    models.CharField(
                        choices=[
                            ("AUD", "Australian Dollar"),
                            ("USD", "US Dollar"),
                            ("EUR", "Euro"),
                            ("GBP", "British Pound"),
                            ("CAD", "Canadian Dollar"),
                            ("JPY", "Japanese Yen"),
                            ("NZD", "New Zealand Dollar"),
                            ("SGD", "Singapore Dollar"),
                        ],
                        default="AUD",
                        max_length=16,
                    ),
                ),
                ("accepts_bank_transfer", models.BooleanField(default=True)),
                ("minimum_shares", models.PositiveIntegerField()),
                ("target_shares", models.PositiveIntegerField()),
                ("cap_shares", models.PositiveIntegerField()),
                ("maximum_shares", models.PositiveIntegerField(blank=True, null=True)),
                ("opens_at", models.DateTimeField()),
                ("closes_at", models.DateTimeField(blank=True, null=True)),
                ("summary", models.TextField(blank=True)),
                ("use_of_proceeds", models.TextField(blank=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_notes", models.TextField(blank=True)),
                ("rejection_reason", models.TextField(blank=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("close_reason", models.TextField(blank=True)),
                (
                    "documents",
                    models.ManyToManyField(blank=True, related_name="offerings", to="companies.companydocument"),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_offerings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "settlement_assets",
                    models.ManyToManyField(
                        blank=True,
                        limit_choices_to={"asset_type": "stablecoin"},
                        related_name="offerings",
                        to="assets.asset",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="submitted_offerings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="offerings", to="tokens.sharetoken"
                    ),
                ),
            ],
            options={
                "verbose_name": "Offering",
                "verbose_name_plural": "Offerings",
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["status", "opens_at"], name="offerings_o_status_80961f_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status__in", ["submitted", "under_review", "approved"])),
                        fields=("token",),
                        name="offering_one_live_per_token",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("minimum_shares__gte", 1),
                            ("target_shares__gte", models.F("minimum_shares")),
                            ("cap_shares__gte", models.F("target_shares")),
                        ),
                        name="offering_bounds_ordered",
                        violation_error_message="Minimum, target and cap must be at least one share and ordered minimum <= target <= cap.",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("closes_at__isnull", True), ("closes_at__gt", models.F("opens_at")), _connector="OR"
                        ),
                        name="offering_window_ordered",
                        violation_error_message="An offering must close after it opens.",
                    ),
                ],
            },
        ),
    ]
