import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("assets", "0011_add_exchange_rate_model"),
    ]

    operations = [
        migrations.CreateModel(
            name="Operator",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("legal_name", models.CharField(blank=True, max_length=255)),
                ("abn", models.CharField(blank=True, max_length=14)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("website", models.URLField(blank=True)),
                (
                    "deployment_mode",
                    models.CharField(
                        choices=[
                            ("single_issuer", "Single issuer (one company on its own instance)"),
                            ("registry", "Registry (many companies on one instance)"),
                        ],
                        default="registry",
                        max_length=20,
                    ),
                ),
                ("bank_account_name", models.CharField(blank=True, max_length=255)),
                ("bank_bsb", models.CharField(blank=True, max_length=7)),
                ("bank_account_number", models.CharField(blank=True, max_length=20)),
                (
                    "payment_reference_prefix",
                    models.CharField(
                        blank=True,
                        help_text="Letters and digits; subscription references start with it.",
                        max_length=16,
                    ),
                ),
                ("receiving_wallet_address", models.CharField(blank=True, max_length=42)),
                (
                    "receiving_wallet_chain",
                    models.CharField(
                        choices=[("ethereum", "Ethereum"), ("base", "Base")], default="base", max_length=20
                    ),
                ),
                ("investor_kyc_required", models.BooleanField(default=True)),
                ("issuer_kyc_required", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "issued_stablecoin",
                    models.ForeignKey(
                        blank=True,
                        limit_choices_to={"asset_type": "stablecoin"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="assets.asset",
                    ),
                ),
                (
                    "supported_settlement_assets",
                    models.ManyToManyField(
                        blank=True, limit_choices_to={"asset_type": "stablecoin"}, related_name="+", to="assets.asset"
                    ),
                ),
            ],
            options={
                "verbose_name": "Operator",
                "verbose_name_plural": "Operator",
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("id", 1)), name="operators_operator_single_row")
                ],
            },
        ),
    ]
