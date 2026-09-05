import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0010_alter_asset_asset_type_alter_asset_current_price_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExchangeRate",
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
                ("base_currency", models.CharField(default="USD", max_length=8)),
                ("target_currency", models.CharField(max_length=8)),
                ("rate", models.DecimalField(decimal_places=10, max_digits=20)),
            ],
            options={
                "indexes": [models.Index(fields=["base_currency", "target_currency"], name="idx_exchange_rate_pair")],
                "unique_together": {("base_currency", "target_currency")},
            },
        ),
    ]
