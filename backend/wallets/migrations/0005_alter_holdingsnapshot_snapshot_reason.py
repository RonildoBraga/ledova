from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0004_wallet_is_operator"),
    ]

    operations = [
        migrations.AlterField(
            model_name="holdingsnapshot",
            name="snapshot_reason",
            field=models.CharField(
                choices=[("TRANSACTION", "Transaction"), ("DAILY", "Daily")], db_index=True, max_length=32
            ),
        ),
    ]
