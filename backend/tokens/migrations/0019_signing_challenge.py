import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0018_protect_the_register_spine"),
    ]

    operations = [
        migrations.CreateModel(
            name="SigningChallenge",
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
                    "purpose",
                    models.CharField(
                        choices=[
                            ("order_cancel", "Order cancel"),
                            ("order_create", "Order create"),
                            ("order_modify", "Order modify"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("wallet_address", models.CharField(db_index=True, max_length=42)),
                ("chain_id", models.PositiveBigIntegerField()),
                ("verifying_contract", models.CharField(max_length=42)),
                ("payload", models.JSONField()),
                ("digest", models.CharField(max_length=66, unique=True)),
                ("nonce", models.PositiveBigIntegerField()),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("consumed_signature", models.CharField(blank=True, max_length=132)),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="signing_challenges",
                        to="tokens.transferorder",
                    ),
                ),
            ],
            options={
                "db_table": "signing_challenges",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["wallet_address", "purpose"], name="signing_cha_wallet__ff224b_idx"),
                    models.Index(fields=["expires_at"], name="signing_cha_expires_5d4df2_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("wallet_address", "nonce"), name="unique_nonce_per_wallet")
                ],
            },
        ),
    ]
