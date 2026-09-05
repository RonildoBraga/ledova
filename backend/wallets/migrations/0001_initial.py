import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("assets", "0001_initial"),
        ("users", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Wallet",
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
                ("address", models.CharField(db_index=True, max_length=255)),
                (
                    "chain",
                    models.CharField(
                        choices=[
                            ("ethereum", "ETHEREUM"),
                            ("bitcoin", "BITCOIN"),
                            ("polygon", "POLYGON"),
                            ("solana", "SOLANA"),
                            ("avalanche", "AVALANCHE"),
                            ("arbitrum", "ARBITRUM"),
                            ("optimism", "OPTIMISM"),
                            ("base", "BASE"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                (
                    "custody_model",
                    models.CharField(
                        choices=[("non_custodial", "Non Custodial")], default="non_custodial", max_length=16
                    ),
                ),
                (
                    "verification_status",
                    models.CharField(
                        choices=[("PENDING", "Pending Verification"), ("VERIFIED", "Verified")],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("verification_challenge", models.TextField(blank=True, null=True)),
                ("verification_signature", models.TextField(blank=True, null=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("is_whitelisted_for_securities", models.BooleanField(default=False)),
                ("whitelisted_at", models.DateTimeField(blank=True, null=True)),
                ("whitelisting_authority", models.CharField(blank=True, max_length=255, null=True)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("last_synced_block", models.BigIntegerField(blank=True, null=True)),
                ("reconstruction_complete", models.BooleanField(default=False)),
                ("reconstruction_completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "reconstruction_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In Progress"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "derivation_path",
                    models.CharField(
                        blank=True,
                        help_text="Full BIP44 derivation path to this address (e.g., m/44'/60'/0'/0/0)",
                        max_length=100,
                        null=True,
                    ),
                ),
                (
                    "master_fingerprint",
                    models.CharField(
                        blank=True, help_text="Hardware wallet identifier (8-char hex)", max_length=8, null=True
                    ),
                ),
                (
                    "address_index",
                    models.IntegerField(
                        blank=True,
                        help_text="Index of this address in the derivation sequence (0, 1, 2, ...)",
                        null=True,
                    ),
                ),
                (
                    "parent_public_key",
                    models.CharField(
                        blank=True,
                        help_text="Public key at external chain level (33-byte compressed, hex)",
                        max_length=66,
                        null=True,
                    ),
                ),
                (
                    "parent_chain_code",
                    models.CharField(
                        blank=True,
                        help_text="Chain code at external chain level (32-byte, hex)",
                        max_length=64,
                        null=True,
                    ),
                ),
                (
                    "parent_derivation_path",
                    models.CharField(
                        blank=True,
                        help_text="Derivation path of the parent key (e.g., m/44'/60'/0'/0)",
                        max_length=100,
                        null=True,
                    ),
                ),
                (
                    "user_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="wallets", to="users.useraccount"
                    ),
                ),
            ],
            options={
                "verbose_name": "Wallet",
                "verbose_name_plural": "Wallets",
                "db_table": "wallets",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Transaction",
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
                ("tx_hash", models.CharField(db_index=True, max_length=255)),
                (
                    "chain",
                    models.CharField(
                        choices=[
                            ("ethereum", "ETHEREUM"),
                            ("bitcoin", "BITCOIN"),
                            ("polygon", "POLYGON"),
                            ("solana", "SOLANA"),
                            ("avalanche", "AVALANCHE"),
                            ("arbitrum", "ARBITRUM"),
                            ("optimism", "OPTIMISM"),
                            ("base", "BASE"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("from_address", models.CharField(db_index=True, max_length=255)),
                ("to_address", models.CharField(blank=True, db_index=True, max_length=255, null=True)),
                ("amount", models.DecimalField(decimal_places=18, max_digits=30)),
                (
                    "market_value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="USD value at transaction time (amount × asset price at block_timestamp)",
                        max_digits=30,
                        null=True,
                    ),
                ),
                ("block_timestamp", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("block_number", models.BigIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("confirmed", "Confirmed"), ("failed", "Failed")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "transaction_fee_estimated",
                    models.DecimalField(blank=True, decimal_places=18, max_digits=30, null=True),
                ),
                ("transaction_fee", models.DecimalField(blank=True, decimal_places=18, max_digits=30, null=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="assets.asset"
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="transactions", to="wallets.wallet"
                    ),
                ),
            ],
            options={
                "verbose_name": "Transaction",
                "verbose_name_plural": "Transactions",
                "db_table": "transactions",
                "ordering": ["-block_timestamp"],
            },
        ),
        migrations.CreateModel(
            name="Holding",
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
                ("quantity", models.DecimalField(decimal_places=18, max_digits=40)),
                ("last_synced_block", models.BigIntegerField(blank=True, null=True)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="holdings", to="assets.asset"
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="holdings", to="wallets.wallet"
                    ),
                ),
            ],
            options={
                "verbose_name": "Holding",
                "verbose_name_plural": "Holdings",
                "db_table": "holdings",
                "ordering": ["-quantity"],
            },
        ),
        migrations.CreateModel(
            name="FiatTransaction",
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
                    "provider",
                    models.CharField(
                        choices=[("MOONPAY", "Moonpay"), ("RAMP", "Ramp Network")], default="RAMP", max_length=20
                    ),
                ),
                ("external_id", models.CharField(db_index=True, max_length=255, unique=True)),
                ("fiat_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("fiat_currency", models.CharField(default="USD", max_length=3)),
                ("crypto_amount", models.DecimalField(blank=True, decimal_places=18, max_digits=30, null=True)),
                ("crypto_currency", models.CharField(max_length=10)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("PROCESSING", "Processing"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "payment_method",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("CARD", "Credit/Debit Card"),
                            ("BANK_TRANSFER", "Bank Transfer"),
                            ("APPLE_PAY", "Apple Pay"),
                            ("GOOGLE_PAY", "Google Pay"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("transaction_hash", models.CharField(blank=True, max_length=255, null=True)),
                ("provider_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("network_fee", models.DecimalField(blank=True, decimal_places=18, max_digits=30, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("failure_reason", models.TextField(blank=True, null=True)),
                ("provider_data", models.JSONField(blank=True, default=dict)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fiat_transactions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fiat_transactions",
                        to="wallets.wallet",
                    ),
                ),
            ],
            options={
                "verbose_name": "Fiat Transaction",
                "verbose_name_plural": "Fiat Transactions",
                "db_table": "fiat_transactions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="HoldingSnapshot",
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
                ("quantity", models.DecimalField(decimal_places=18, max_digits=40)),
                ("block_number", models.BigIntegerField(blank=True, null=True)),
                ("snapshot_date", models.DateField(db_index=True)),
                (
                    "snapshot_reason",
                    models.CharField(
                        choices=[
                            ("BALANCE_SYNC", "Balance Sync"),
                            ("TRANSACTION", "Transaction"),
                            ("DAILY", "Daily"),
                            ("MANUAL", "Manual"),
                            ("RECONSTRUCTION", "Reconstruction"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                (
                    "holding",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="snapshots", to="wallets.holding"
                    ),
                ),
                (
                    "caused_by_transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="holding_snapshots",
                        to="wallets.transaction",
                    ),
                ),
            ],
            options={
                "verbose_name": "Holding Snapshot",
                "verbose_name_plural": "Holding Snapshots",
                "db_table": "holding_snapshots",
                "ordering": ["-snapshot_date"],
                "indexes": [
                    models.Index(fields=["holding", "-snapshot_date"], name="idx_hsnap_hold_date"),
                    models.Index(fields=["snapshot_date"], name="idx_hsnap_date"),
                    models.Index(fields=["snapshot_reason"], name="idx_hsnap_reason"),
                    models.Index(fields=["holding", "snapshot_reason"], name="idx_hsnap_hold_reason"),
                ],
                "unique_together": {("holding", "snapshot_date")},
            },
        ),
        migrations.AddIndex(
            model_name="wallet",
            index=models.Index(fields=["user_account", "verification_status"], name="wallets_user_ac_11eac8_idx"),
        ),
        migrations.AddIndex(
            model_name="wallet",
            index=models.Index(fields=["chain"], name="wallets_chain_16c273_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="wallet",
            unique_together={("user_account", "address")},
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["tx_hash"], name="transaction_tx_hash_630f6e_idx"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["from_address"], name="transaction_from_ad_b319de_idx"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["to_address"], name="transaction_to_addr_75c298_idx"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["wallet", "-block_timestamp"], name="transaction_wallet__e10127_idx"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["chain", "-block_timestamp"], name="transaction_chain_c40788_idx"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["status"], name="transaction_status_505a2f_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="transaction",
            unique_together={("tx_hash", "wallet")},
        ),
        migrations.AddIndex(
            model_name="holding",
            index=models.Index(fields=["wallet"], name="idx_holding_wallet"),
        ),
        migrations.AddIndex(
            model_name="holding",
            index=models.Index(fields=["asset"], name="idx_holding_asset"),
        ),
        migrations.AddConstraint(
            model_name="holding",
            constraint=models.UniqueConstraint(fields=("wallet", "asset"), name="unique_wallet_asset"),
        ),
        migrations.AddIndex(
            model_name="fiattransaction",
            index=models.Index(fields=["external_id"], name="fiat_transa_externa_b494f4_idx"),
        ),
        migrations.AddIndex(
            model_name="fiattransaction",
            index=models.Index(fields=["wallet", "-created_at"], name="fiat_transa_wallet__790910_idx"),
        ),
        migrations.AddIndex(
            model_name="fiattransaction",
            index=models.Index(fields=["user", "-created_at"], name="fiat_transa_user_id_6e8035_idx"),
        ),
        migrations.AddIndex(
            model_name="fiattransaction",
            index=models.Index(fields=["status"], name="fiat_transa_status_9b1cf7_idx"),
        ),
    ]
