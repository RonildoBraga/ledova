import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("blockchain", "0001_initial"),
        ("companies", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Stablecoin",
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
                ("symbol", models.CharField(max_length=10, unique=True)),
                ("contract_address", models.CharField(max_length=42, unique=True)),
                ("decimals", models.PositiveSmallIntegerField(default=2)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Stablecoin",
                "verbose_name_plural": "Stablecoins",
                "ordering": ["symbol"],
            },
        ),
        migrations.CreateModel(
            name="ShareToken",
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
                ("symbol", models.CharField(max_length=10)),
                (
                    "token_type",
                    models.CharField(
                        choices=[("ordinary", "Ordinary"), ("preference", "Preference"), ("redeemable", "Redeemable")],
                        default="ordinary",
                        max_length=20,
                    ),
                ),
                ("total_supply", models.CharField(max_length=78)),
                ("decimals", models.PositiveSmallIntegerField(default=0)),
                ("is_transferable", models.BooleanField(default=True)),
                ("is_divisible", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("deploying", "Deploying"),
                            ("deployed", "Deployed"),
                            ("paused", "Paused"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("contract_address", models.CharField(blank=True, max_length=42, null=True, unique=True)),
                (
                    "deployment_tx_hash",
                    models.CharField(
                        blank=True, help_text="Transaction hash of deployment (legacy field)", max_length=66, null=True
                    ),
                ),
                ("deployed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="tokens", to="companies.company"
                    ),
                ),
                (
                    "deployment_transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deployed_share_tokens",
                        to="blockchain.blockchaintransaction",
                    ),
                ),
            ],
            options={
                "verbose_name": "Share Token",
                "verbose_name_plural": "Share Tokens",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="StablecoinMintRequest",
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
                    "recipient_address",
                    models.CharField(help_text="Wallet address to receive the minted tokens", max_length=42),
                ),
                (
                    "recipient_name",
                    models.CharField(help_text="Name of the recipient (for audit purposes)", max_length=200),
                ),
                ("amount", models.PositiveIntegerField(help_text="Amount to mint in cents (e.g., 10000 = $100.00)")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("executed", "Executed"),
                            ("failed", "Failed"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "deposit_reference",
                    models.CharField(help_text="Bank reference or transaction ID for the fiat deposit", max_length=100),
                ),
                ("deposit_date", models.DateField(help_text="Date the fiat deposit was received")),
                (
                    "executed_at",
                    models.DateTimeField(blank=True, help_text="Timestamp when the mint was executed", null=True),
                ),
                ("notes", models.TextField(blank=True, help_text="Additional notes about this mint request")),
                ("rejection_reason", models.TextField(blank=True, help_text="Reason for rejection (if rejected)")),
                ("error_message", models.TextField(blank=True, help_text="Error message if mint failed")),
                (
                    "executed_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Staff member who executed this request",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stablecoin_mint_requests_executed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        help_text="Staff member who created this request",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stablecoin_mint_requests_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "stablecoin",
                    models.ForeignKey(
                        help_text="The stablecoin being minted",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mint_requests",
                        to="tokens.stablecoin",
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stablecoin_mint_requests",
                        to="blockchain.blockchaintransaction",
                    ),
                ),
            ],
            options={
                "verbose_name": "Stablecoin Mint Request",
                "verbose_name_plural": "Stablecoin Mint Requests",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TokenIssuance",
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
                    "recipient_address",
                    models.CharField(help_text="Ethereum address receiving the shares (0x...)", max_length=42),
                ),
                (
                    "recipient_name",
                    models.CharField(blank=True, help_text="Optional name/label for the recipient", max_length=255),
                ),
                (
                    "amount",
                    models.CharField(help_text="Number of shares issued (as string for large numbers)", max_length=78),
                ),
                (
                    "issuance_type",
                    models.CharField(
                        choices=[
                            ("initial", "Initial Issuance"),
                            ("additional", "Additional Issuance"),
                            ("bonus", "Bonus Shares"),
                            ("dividend", "Dividend Reinvestment"),
                            ("transfer", "Transfer (Re-issuance)"),
                        ],
                        default="additional",
                        max_length=20,
                    ),
                ),
                ("reason", models.TextField(blank=True, help_text="Reason or notes for the issuance")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("error_message", models.TextField(blank=True, help_text="Error details if issuance failed")),
                (
                    "tx_hash",
                    models.CharField(
                        blank=True,
                        help_text="Transaction hash of the issuance (legacy field)",
                        max_length=66,
                        null=True,
                    ),
                ),
                (
                    "block_number",
                    models.PositiveBigIntegerField(
                        blank=True, help_text="Block number where transaction was mined (legacy field)", null=True
                    ),
                ),
                (
                    "gas_used",
                    models.PositiveBigIntegerField(
                        blank=True, help_text="Gas used by the transaction (legacy field)", null=True
                    ),
                ),
                (
                    "processed_at",
                    models.DateTimeField(
                        blank=True, help_text="When the blockchain transaction was submitted", null=True
                    ),
                ),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True, help_text="When the blockchain transaction was confirmed", null=True
                    ),
                ),
                (
                    "idempotency_key",
                    models.CharField(
                        blank=True,
                        help_text="Unique key to prevent duplicate issuances",
                        max_length=64,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    "initiated_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who initiated the issuance",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="initiated_issuances",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="issuances", to="tokens.sharetoken"
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="token_issuances",
                        to="blockchain.blockchaintransaction",
                    ),
                ),
            ],
            options={
                "verbose_name": "Token Issuance",
                "verbose_name_plural": "Token Issuances",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CapitalIncreaseRequest",
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
                    "additional_shares",
                    models.PositiveIntegerField(help_text="Number of additional shares to authorize and mint"),
                ),
                (
                    "new_authorized_total",
                    models.PositiveIntegerField(help_text="New total authorized shares after increase"),
                ),
                ("purpose", models.TextField(help_text="Purpose or justification for this capital increase")),
                (
                    "board_resolution_reference",
                    models.CharField(
                        help_text="Reference to board resolution authorizing this increase", max_length=255
                    ),
                ),
                (
                    "shareholder_approval_reference",
                    models.CharField(
                        blank=True, help_text="Reference to shareholder approval (if required)", max_length=255
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("submitted", "Submitted"),
                            ("under_review", "Under Review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("executing", "Executing"),
                            ("executed", "Executed"),
                            ("failed", "Failed"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                (
                    "dilution_percentage",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Percentage dilution this increase would cause to existing holders",
                        max_digits=5,
                        null=True,
                    ),
                ),
                (
                    "submitted_at",
                    models.DateTimeField(blank=True, help_text="When the request was submitted", null=True),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, help_text="When the request was reviewed", null=True)),
                ("review_notes", models.TextField(blank=True, help_text="Notes from the reviewer")),
                ("rejection_reason", models.TextField(blank=True, help_text="Reason for rejection (if rejected)")),
                (
                    "executed_at",
                    models.DateTimeField(
                        blank=True, help_text="When the capital increase was executed on-chain", null=True
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Staff member who reviewed the request",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_capital_increases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who submitted the request",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="submitted_capital_increases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="capital_increase_requests",
                        to="tokens.sharetoken",
                    ),
                ),
                (
                    "executed_issuance",
                    models.OneToOneField(
                        blank=True,
                        help_text="The executed TokenIssuance record for the minted shares",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="capital_increase",
                        to="tokens.tokenissuance",
                    ),
                ),
            ],
            options={
                "verbose_name": "Capital Increase Request",
                "verbose_name_plural": "Capital Increase Requests",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TransferOrder",
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
                ("order_type", models.CharField(choices=[("buy", "Buy"), ("sell", "Sell")], max_length=10)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("partially_filled", "Partially Filled"),
                            ("matched", "Matched"),
                            ("pending_signature", "Pending Signature"),
                            ("executing", "Executing"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                            ("failed", "Failed"),
                        ],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("wallet_address", models.CharField(max_length=42)),
                ("quantity", models.PositiveBigIntegerField()),
                ("price_per_share", models.DecimalField(decimal_places=2, max_digits=18)),
                (
                    "min_quantity",
                    models.PositiveBigIntegerField(
                        default=0,
                        help_text="Minimum quantity per fill. 0 means exact match only (min_quantity = remaining).",
                    ),
                ),
                (
                    "filled_quantity",
                    models.PositiveBigIntegerField(
                        default=0, help_text="Total quantity already filled across all partial fills."
                    ),
                ),
                (
                    "original_quantity",
                    models.PositiveBigIntegerField(
                        blank=True,
                        help_text="Original quantity at order creation (set on first modification).",
                        null=True,
                    ),
                ),
                (
                    "original_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Original price at order creation (set on first modification).",
                        max_digits=18,
                        null=True,
                    ),
                ),
                (
                    "modification_count",
                    models.PositiveIntegerField(default=0, help_text="Number of times this order has been modified."),
                ),
                (
                    "last_modified_at",
                    models.DateTimeField(blank=True, help_text="Timestamp of the most recent modification.", null=True),
                ),
                (
                    "current_signature",
                    models.TextField(
                        blank=True, help_text="Signature from the most recent modification (or creation if unmodified)."
                    ),
                ),
                ("exchange_order_id", models.CharField(blank=True, max_length=66)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("tx_hash", models.CharField(blank=True, max_length=66)),
                ("error_message", models.TextField(blank=True)),
                (
                    "matched_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="matched_by",
                        to="tokens.transferorder",
                    ),
                ),
                (
                    "payment_token",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="transfer_orders",
                        to="tokens.stablecoin",
                    ),
                ),
                (
                    "signature_request",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="transfer_orders",
                        to="companies.signaturerequest",
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transfer_orders",
                        to="tokens.sharetoken",
                    ),
                ),
            ],
            options={
                "verbose_name": "Transfer Order",
                "verbose_name_plural": "Transfer Orders",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SwapOrder",
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
                ("seller_address", models.CharField(max_length=42)),
                ("buyer_address", models.CharField(max_length=42)),
                (
                    "share_amount",
                    models.PositiveBigIntegerField(help_text="Number of shares to transfer (no decimals)"),
                ),
                (
                    "payment_amount",
                    models.PositiveBigIntegerField(
                        help_text="Payment amount in stablecoin smallest units (e.g., cents for 2 decimals)"
                    ),
                ),
                ("nonce", models.PositiveBigIntegerField(help_text="Unique nonce for replay protection")),
                ("order_hash", models.CharField(help_text="EIP-712 typed data hash", max_length=66, unique=True)),
                ("seller_signature", models.TextField(blank=True, help_text="EIP-712 signature from seller")),
                ("buyer_signature", models.TextField(blank=True, help_text="EIP-712 signature from buyer")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("seller_signed", "Seller Signed"),
                            ("buyer_signed", "Buyer Signed"),
                            ("ready", "Ready for Execution"),
                            ("executing", "Executing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("expired", "Expired"),
                        ],
                        default="created",
                        max_length=20,
                    ),
                ),
                ("expires_at", models.DateTimeField()),
                (
                    "tx_hash",
                    models.CharField(
                        blank=True, help_text="Transaction hash when executed on-chain (legacy field)", max_length=66
                    ),
                ),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                (
                    "payment_token",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="swap_orders", to="tokens.stablecoin"
                    ),
                ),
                (
                    "share_token",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="swap_orders", to="tokens.sharetoken"
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="swap_orders",
                        to="blockchain.blockchaintransaction",
                    ),
                ),
                (
                    "buy_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="swap_as_buy",
                        to="tokens.transferorder",
                    ),
                ),
                (
                    "sell_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="swap_as_sell",
                        to="tokens.transferorder",
                    ),
                ),
            ],
            options={
                "verbose_name": "Swap Order",
                "verbose_name_plural": "Swap Orders",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="OrderModificationLog",
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
                    "field_name",
                    models.CharField(
                        help_text="Name of the field that was modified (e.g., 'quantity', 'price_per_share').",
                        max_length=50,
                    ),
                ),
                ("old_value", models.CharField(help_text="The value before modification.", max_length=100)),
                ("new_value", models.CharField(help_text="The value after modification.", max_length=100)),
                (
                    "modification_message",
                    models.TextField(help_text="The message that was signed to authorize this modification."),
                ),
                ("signature", models.TextField(help_text="The cryptographic signature authorizing this modification.")),
                (
                    "signer_address",
                    models.CharField(help_text="The wallet address that signed the modification.", max_length=42),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(
                        blank=True, help_text="IP address of the request that made this modification.", null=True
                    ),
                ),
                ("user_agent", models.TextField(blank=True, help_text="User agent string from the request.")),
                (
                    "order",
                    models.ForeignKey(
                        help_text="The order that was modified.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="modification_logs",
                        to="tokens.transferorder",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order Modification Log",
                "verbose_name_plural": "Order Modification Logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="sharetoken",
            constraint=models.UniqueConstraint(fields=("company", "symbol"), name="unique_company_symbol"),
        ),
        migrations.AddIndex(
            model_name="stablecoinmintrequest",
            index=models.Index(fields=["status"], name="tokens_stab_status_4c5fd9_idx"),
        ),
        migrations.AddIndex(
            model_name="stablecoinmintrequest",
            index=models.Index(fields=["deposit_reference"], name="tokens_stab_deposit_7fc908_idx"),
        ),
        migrations.AddIndex(
            model_name="stablecoinmintrequest",
            index=models.Index(fields=["recipient_address"], name="tokens_stab_recipie_dc716d_idx"),
        ),
        migrations.AddIndex(
            model_name="tokenissuance",
            index=models.Index(fields=["token", "status"], name="tokens_toke_token_i_b76d43_idx"),
        ),
        migrations.AddIndex(
            model_name="tokenissuance",
            index=models.Index(fields=["recipient_address"], name="tokens_toke_recipie_783be6_idx"),
        ),
        migrations.AddIndex(
            model_name="tokenissuance",
            index=models.Index(fields=["tx_hash"], name="tokens_toke_tx_hash_27ba2b_idx"),
        ),
        migrations.AddIndex(
            model_name="capitalincreaserequest",
            index=models.Index(fields=["token", "status"], name="tokens_capi_token_i_e6b6f8_idx"),
        ),
        migrations.AddIndex(
            model_name="capitalincreaserequest",
            index=models.Index(fields=["status"], name="tokens_capi_status_2e7f84_idx"),
        ),
        migrations.AddIndex(
            model_name="transferorder",
            index=models.Index(fields=["token", "status"], name="tokens_tran_token_i_2d56dc_idx"),
        ),
        migrations.AddIndex(
            model_name="transferorder",
            index=models.Index(fields=["wallet_address"], name="tokens_tran_wallet__ea7fe6_idx"),
        ),
        migrations.AddIndex(
            model_name="transferorder",
            index=models.Index(fields=["order_type", "status"], name="tokens_tran_order_t_944477_idx"),
        ),
        migrations.AddIndex(
            model_name="swaporder",
            index=models.Index(fields=["status"], name="tokens_swap_status_3b2095_idx"),
        ),
        migrations.AddIndex(
            model_name="swaporder",
            index=models.Index(fields=["seller_address"], name="tokens_swap_seller__d9b2e1_idx"),
        ),
        migrations.AddIndex(
            model_name="swaporder",
            index=models.Index(fields=["buyer_address"], name="tokens_swap_buyer_a_67185b_idx"),
        ),
        migrations.AddIndex(
            model_name="swaporder",
            index=models.Index(fields=["expires_at"], name="tokens_swap_expires_5642fe_idx"),
        ),
        migrations.AddIndex(
            model_name="swaporder",
            index=models.Index(fields=["share_token", "status"], name="tokens_swap_share_t_a18876_idx"),
        ),
        migrations.AddIndex(
            model_name="ordermodificationlog",
            index=models.Index(fields=["order", "created_at"], name="tokens_orde_order_i_eb9ab0_idx"),
        ),
        migrations.AddIndex(
            model_name="ordermodificationlog",
            index=models.Index(fields=["signer_address"], name="tokens_orde_signer__b71cce_idx"),
        ),
        migrations.AddIndex(
            model_name="ordermodificationlog",
            index=models.Index(fields=["field_name"], name="tokens_orde_field_n_b2e7f3_idx"),
        ),
    ]
