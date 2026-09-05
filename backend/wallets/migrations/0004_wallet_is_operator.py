from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0003_update_fiat_transaction_provider_to_transak"),
    ]

    operations = [
        migrations.AddField(
            model_name="wallet",
            name="is_operator",
            field=models.BooleanField(
                default=False,
                help_text="Designates this wallet as a company operator wallet for signing token operations",
            ),
        ),
    ]
