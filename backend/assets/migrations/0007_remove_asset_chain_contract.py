from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0006_populate_chain_deployments"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="asset",
            name="idx_asset_chain_contract",
        ),
        migrations.RemoveField(
            model_name="asset",
            name="chain",
        ),
        migrations.RemoveField(
            model_name="asset",
            name="contract_address",
        ),
    ]
