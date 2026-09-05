import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("wallets", "0004_wallet_is_operator"),
    ]

    operations = [
        migrations.CreateModel(
            name="WhitelistEntry",
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
                            ("pending", "Pending"),
                            ("active", "Active"),
                            ("removed", "Removed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("is_whitelisted", models.BooleanField(default=False)),
                ("on_chain_timestamp", models.DateTimeField(blank=True, null=True)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("add_tx_hash", models.CharField(blank=True, max_length=66, null=True)),
                ("remove_tx_hash", models.CharField(blank=True, max_length=66, null=True)),
                ("notes", models.TextField(blank=True)),
                (
                    "wallet",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, related_name="whitelist_entry", to="wallets.wallet"
                    ),
                ),
            ],
            options={
                "verbose_name": "Whitelist Entry",
                "verbose_name_plural": "Whitelist Entries",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["status"], name="whitelist_w_status_17a99e_idx"),
                    models.Index(fields=["is_whitelisted"], name="whitelist_w_is_whit_d18750_idx"),
                ],
            },
        ),
    ]
