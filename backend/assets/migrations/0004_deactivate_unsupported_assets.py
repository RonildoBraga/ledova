from django.db import migrations

UNSUPPORTED_SYMBOLS = ["AAVE", "COMP", "LINK", "MKR", "SNX", "UNI", "DAI"]


def deactivate_unsupported_assets(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    Asset.objects.filter(symbol__in=UNSUPPORTED_SYMBOLS).update(is_active=False)


def reactivate_assets(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    Asset.objects.filter(symbol__in=UNSUPPORTED_SYMBOLS).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0003_rename_aaud_asset"),
    ]

    operations = [
        migrations.RunPython(deactivate_unsupported_assets, reactivate_assets),
    ]
