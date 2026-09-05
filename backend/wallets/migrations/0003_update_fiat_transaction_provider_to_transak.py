from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0002_wallet_wallet_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fiattransaction",
            name="provider",
            field=models.CharField(choices=[("TRANSAK", "Transak")], default="TRANSAK", max_length=20),
        ),
    ]
