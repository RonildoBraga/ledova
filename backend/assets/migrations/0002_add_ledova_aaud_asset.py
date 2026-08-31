# Generated data migration for a synthetic aAUD example asset.

from decimal import Decimal

from django.db import migrations


def create_aaud_asset(apps, schema_editor):
    """Create a synthetic aAUD asset for local/testnet demonstrations."""
    Asset = apps.get_model("assets", "Asset")

    Asset.objects.get_or_create(
        symbol="aAUD",
        defaults={
            "name": "Synthetic AUD Example Token",
            "asset_type": "stablecoin",
            "chain": "ledova",
            "decimals": 2,
            "current_price": Decimal("1.00"),
            "price_currency": "USD",
            "is_active": True,
        },
    )


def remove_aaud_asset(apps, schema_editor):
    """Remove the aAUD asset (reverse migration)."""
    Asset = apps.get_model("assets", "Asset")
    Asset.objects.filter(symbol="aAUD", chain="ledova").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_aaud_asset, remove_aaud_asset),
    ]
