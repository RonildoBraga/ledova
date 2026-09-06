import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0012_audy_base_deployment"),
        ("offerings", "0001_initial"),
        ("tokens", "0016_drop_stablecoin"),
        ("users", "0018_investor_classification"),
        ("wallets", "0006_delete_fiattransaction_drop_unread_columns"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Subscription",
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
                ("quantity", models.PositiveIntegerField()),
                ("allotted_quantity", models.PositiveIntegerField(blank=True, null=True)),
                ("price_per_share", models.DecimalField(decimal_places=2, max_digits=18)),
                ("amount_due", models.DecimalField(decimal_places=2, max_digits=18)),
                (
                    "settlement_rail",
                    models.CharField(
                        choices=[("bank_transfer", "Bank transfer"), ("stablecoin", "Stablecoin")],
                        default="bank_transfer",
                        max_length=20,
                    ),
                ),
                ("settlement_amount", models.BigIntegerField(blank=True, null=True)),
                ("reference", models.CharField(blank=True, max_length=18)),
                ("payment_instruction_issued_at", models.DateTimeField(blank=True, null=True)),
                ("payment_due_at", models.DateTimeField(blank=True, null=True)),
                ("amount_received", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("payment_received_on", models.DateField(blank=True, null=True)),
                ("payment_reference_seen", models.CharField(blank=True, max_length=140)),
                ("payment_tx_hash", models.CharField(blank=True, max_length=66)),
                ("payment_confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("payment_notes", models.TextField(blank=True)),
                ("refund_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("refunded_at", models.DateTimeField(blank=True, null=True)),
                ("refund_reference", models.CharField(blank=True, max_length=140)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("submitted", "Submitted"),
                            ("accepted", "Accepted"),
                            ("awaiting_payment", "Awaiting Payment"),
                            ("paid", "Paid"),
                            ("allotted", "Allotted"),
                            ("rejected", "Rejected"),
                            ("withdrawn", "Withdrawn"),
                            ("refunded", "Refunded"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                (
                    "issuance_request",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subscription",
                        to="tokens.shareissuancerequest",
                    ),
                ),
                (
                    "offering",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="offerings.offering",
                    ),
                ),
                (
                    "payment_confirmed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="confirmed_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "settlement_asset",
                    models.ForeignKey(
                        blank=True,
                        limit_choices_to={"asset_type": "stablecoin"},
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="assets.asset",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="submitted_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="users.useraccount",
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="wallets.wallet"
                    ),
                ),
            ],
            options={
                "verbose_name": "Subscription",
                "verbose_name_plural": "Subscriptions",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["offering", "status"], name="offerings_s_offerin_897ac7_idx"),
                    models.Index(fields=["status"], name="offerings_s_status_c64bbb_idx"),
                    models.Index(fields=["reference"], name="offerings_s_referen_83a6e8_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("reference", ""), _negated=True),
                        fields=("reference",),
                        name="subscription_reference_unique",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("payment_tx_hash", ""), _negated=True),
                        fields=("payment_tx_hash",),
                        name="subscription_payment_tx_hash_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("quantity__gt", 0)),
                        name="subscription_quantity_positive",
                        violation_error_message="A subscription must ask for at least one share.",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("allotted_quantity__isnull", True),
                            ("allotted_quantity__lte", models.F("quantity")),
                            _connector="OR",
                        ),
                        name="subscription_allotted_within_quantity",
                        violation_error_message="A subscription cannot be allotted more shares than it asked for.",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("settlement_asset__isnull", True), ("settlement_rail", "bank_transfer")),
                            models.Q(("settlement_asset__isnull", False), ("settlement_rail", "stablecoin")),
                            _connector="OR",
                        ),
                        name="subscription_rail_matches_settlement_asset",
                        violation_error_message="A bank transfer carries no settlement asset, and a stablecoin settlement must name one.",
                    ),
                ],
            },
        ),
    ]
