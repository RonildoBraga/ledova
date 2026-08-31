import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0004_deactivate_unsupported_assets"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssetChainDeployment",
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
                    "chain",
                    models.CharField(
                        help_text="Blockchain (ethereum, base, bitcoin, etc.)",
                        max_length=32,
                    ),
                ),
                (
                    "contract_address",
                    models.CharField(
                        blank=True,
                        help_text="Contract address on this chain (null for native assets like ETH, BTC)",
                        max_length=128,
                        null=True,
                    ),
                ),
                (
                    "decimals",
                    models.IntegerField(default=18, help_text="Token decimals on this chain"),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chain_deployments",
                        to="assets.asset",
                    ),
                ),
            ],
            options={
                "verbose_name": "Asset Chain Deployment",
                "verbose_name_plural": "Asset Chain Deployments",
                "db_table": "asset_chain_deployments",
                "ordering": ["asset", "chain"],
            },
        ),
        migrations.AddIndex(
            model_name="assetchaindeployment",
            index=models.Index(
                fields=["chain", "contract_address"],
                name="idx_deploy_chain_contract",
            ),
        ),
        migrations.AddConstraint(
            model_name="assetchaindeployment",
            constraint=models.UniqueConstraint(
                fields=("asset", "chain"),
                name="unique_asset_chain",
            ),
        ),
        migrations.AddConstraint(
            model_name="assetchaindeployment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("contract_address__isnull", False)),
                fields=("chain", "contract_address"),
                name="unique_chain_contract",
            ),
        ),
    ]
