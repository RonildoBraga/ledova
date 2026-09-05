from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0009_verify_supported_assets_cleanup_spam"),
    ]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="asset_type",
            field=models.CharField(
                choices=[
                    ("native_crypto", "Native Crypto"),
                    ("erc20_token", "Erc20 Token"),
                    ("stablecoin", "Stablecoin"),
                    ("tokenized_security", "Tokenized Security"),
                    ("tokenized_rwa", "Tokenized Rwa"),
                    ("synthetic", "Synthetic"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="current_price",
            field=models.DecimalField(blank=True, decimal_places=18, max_digits=40, null=True),
        ),
        migrations.AlterField(
            model_name="asset",
            name="decimals",
            field=models.IntegerField(default=18),
        ),
        migrations.AlterField(
            model_name="asset",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="asset",
            name="name",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="asset",
            name="price_currency",
            field=models.CharField(default="USD", max_length=16),
        ),
        migrations.AlterField(
            model_name="asset",
            name="symbol",
            field=models.CharField(db_index=True, max_length=32, unique=True),
        ),
    ]
