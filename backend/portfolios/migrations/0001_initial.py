import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("assets", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Portfolio",
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
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Portfolio",
                "verbose_name_plural": "Portfolios",
                "db_table": "portfolios",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PortfolioSnapshot",
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
                ("snapshot_date", models.DateField()),
                (
                    "snapshot_reason",
                    models.CharField(
                        choices=[("DAILY", "Daily Snapshot"), ("MANUAL", "Manual Snapshot")], max_length=50
                    ),
                ),
                ("holdings_data", models.JSONField(blank=True, default=dict)),
                ("total_market_value", models.DecimalField(blank=True, decimal_places=18, max_digits=40, null=True)),
            ],
            options={
                "verbose_name": "Portfolio Snapshot",
                "verbose_name_plural": "Portfolio Snapshots",
                "db_table": "portfolio_snapshots",
            },
        ),
        migrations.CreateModel(
            name="PortfolioTemplate",
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
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "risk_level",
                    models.CharField(
                        choices=[("LOW", "Low Risk"), ("MEDIUM", "Medium Risk"), ("HIGH", "High Risk")],
                        default="MEDIUM",
                        max_length=10,
                    ),
                ),
            ],
            options={
                "verbose_name": "Portfolio Template",
                "verbose_name_plural": "Portfolio Templates",
                "db_table": "portfolio_templates",
            },
        ),
        migrations.CreateModel(
            name="TargetAssetAllocation",
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
                    "percentage",
                    models.DecimalField(
                        decimal_places=2, help_text="Target allocation percentage (0-100)", max_digits=5
                    ),
                ),
            ],
            options={
                "verbose_name": "Target Asset Allocation",
                "verbose_name_plural": "Target Asset Allocations",
                "db_table": "target_asset_allocations",
            },
        ),
        migrations.CreateModel(
            name="AssetAllocation",
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
                ("percentage", models.DecimalField(decimal_places=2, max_digits=5)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="assets.asset")),
            ],
            options={
                "verbose_name": "Asset Allocation",
                "verbose_name_plural": "Asset Allocations",
                "db_table": "asset_allocations",
            },
        ),
    ]
