from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0007_remove_asset_chain_contract"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="is_verified",
            field=models.BooleanField(default=False),
        ),
    ]
