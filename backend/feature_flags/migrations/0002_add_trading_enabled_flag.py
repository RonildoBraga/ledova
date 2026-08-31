from django.db import migrations


def create_trading_flag(apps, schema_editor):
    FeatureFlag = apps.get_model("feature_flags", "FeatureFlag")
    FeatureFlag.objects.get_or_create(
        name="trading_enabled",
        defaults={
            "description": "Enables P2P trading of share tokens (buy/sell orders, atomic swaps)",
            "enabled": False,
            "platform": "all",
        },
    )


def remove_trading_flag(apps, schema_editor):
    FeatureFlag = apps.get_model("feature_flags", "FeatureFlag")
    FeatureFlag.objects.filter(name="trading_enabled").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("feature_flags", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_trading_flag, remove_trading_flag),
    ]
