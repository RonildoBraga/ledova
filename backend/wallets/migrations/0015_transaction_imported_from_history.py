from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wallets", "0014_wallet_network_identity")]
    operations = [
        migrations.AddField(
            model_name="transaction",
            name="imported_from_history",
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
