import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BlockchainTransaction",
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
                ("tx_hash", models.CharField(blank=True, max_length=66, null=True, unique=True)),
                (
                    "tx_type",
                    models.CharField(
                        choices=[
                            ("whitelist_add", "Add to Whitelist"),
                            ("whitelist_remove", "Remove from Whitelist"),
                            ("whitelist_update", "Update Investor Type"),
                            ("token_deploy", "Deploy Token"),
                            ("token_mint", "Mint Tokens"),
                            ("token_transfer", "Transfer Tokens"),
                            ("token_burn", "Burn Tokens"),
                            ("stablecoin_mint", "Mint Stablecoin"),
                            ("stablecoin_burn", "Burn Stablecoin"),
                            ("atomic_swap", "Atomic Swap"),
                            ("share_token_deploy", "Deploy Share Token"),
                            ("contract_deploy", "Deploy Contract"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("submitted", "Submitted"),
                            ("confirmed", "Confirmed"),
                            ("failed", "Failed"),
                            ("reverted", "Reverted"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("from_address", models.CharField(max_length=42)),
                ("to_address", models.CharField(blank=True, max_length=42, null=True)),
                ("value", models.DecimalField(decimal_places=18, default=0, max_digits=36)),
                ("gas_limit", models.PositiveIntegerField(blank=True, null=True)),
                ("gas_price", models.DecimalField(blank=True, decimal_places=18, max_digits=36, null=True)),
                ("gas_used", models.PositiveIntegerField(blank=True, null=True)),
                ("nonce", models.PositiveIntegerField(blank=True, null=True)),
                ("block_number", models.PositiveIntegerField(blank=True, null=True)),
                ("block_hash", models.CharField(blank=True, max_length=66, null=True)),
                ("function_name", models.CharField(blank=True, max_length=100, null=True)),
                ("function_args", models.JSONField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("retry_count", models.PositiveSmallIntegerField(default=0)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("related_model", models.CharField(blank=True, max_length=100, null=True)),
                ("related_uuid", models.UUIDField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Blockchain Transaction",
                "verbose_name_plural": "Blockchain Transactions",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["tx_hash"], name="blockchain__tx_hash_7a315c_idx"),
                    models.Index(fields=["status"], name="blockchain__status_096a5b_idx"),
                    models.Index(fields=["tx_type"], name="blockchain__tx_type_6dc441_idx"),
                    models.Index(fields=["from_address"], name="blockchain__from_ad_121d3a_idx"),
                    models.Index(fields=["to_address"], name="blockchain__to_addr_9aa631_idx"),
                    models.Index(fields=["block_number"], name="blockchain__block_n_035750_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ContractDeployment",
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
                ("name", models.CharField(max_length=100)),
                ("address", models.CharField(max_length=42, unique=True)),
                ("version", models.CharField(default="1.0.0", max_length=20)),
                ("deployer_address", models.CharField(max_length=42)),
                ("block_number", models.PositiveIntegerField()),
                ("abi_hash", models.CharField(blank=True, max_length=66, null=True)),
                ("constructor_args", models.JSONField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("is_verified", models.BooleanField(default=False)),
                ("chain_id", models.PositiveIntegerField(default=1337)),
                (
                    "deployment_tx",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deployed_contract",
                        to="blockchain.blockchaintransaction",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contract Deployment",
                "verbose_name_plural": "Contract Deployments",
                "ordering": ["-created_at"],
                "unique_together": {("name", "chain_id", "version")},
            },
        ),
    ]
