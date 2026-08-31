from django.db import migrations


def rename_aaud_asset(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    Asset.objects.filter(symbol="aAUD", chain="ledova").update(name="Synthetic AUD Example Token")


def revert_aaud_name(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    Asset.objects.filter(symbol="aAUD", chain="ledova").update(name="Synthetic AUD Example Token")


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0002_add_ledova_aaud_asset"),
    ]

    operations = [
        migrations.RunPython(rename_aaud_asset, revert_aaud_name),
    ]
