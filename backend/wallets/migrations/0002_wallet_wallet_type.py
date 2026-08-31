from django.db import migrations, models


def backfill_wallet_type(apps, schema_editor):
    """Set wallet_type='hardware' for wallets that have a master_fingerprint (hardware wallet indicator)."""
    Wallet = apps.get_model("wallets", "Wallet")
    Wallet.objects.filter(master_fingerprint__isnull=False).update(wallet_type="hardware")


def reverse_backfill(apps, schema_editor):
    """Reverse: reset all wallet_type back to hardware."""
    Wallet = apps.get_model("wallets", "Wallet")
    Wallet.objects.all().update(wallet_type="hardware")


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="wallet",
            name="wallet_type",
            field=models.CharField(
                choices=[
                    ("hardware", "Hardware"),
                    ("software", "Software"),
                ],
                default="hardware",
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_wallet_type, reverse_backfill),
    ]
