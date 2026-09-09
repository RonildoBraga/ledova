from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("assets", "0012_audy_base_deployment")]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="price_source",
            field=models.CharField(
                choices=[("market", "Market price"), ("nav", "NAV"), ("par", "Par")],
                max_length=12,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="price_source",
            field=models.CharField(
                choices=[("market", "Market price"), ("nav", "NAV"), ("par", "Par")],
                default="market",
                max_length=12,
                null=True,
            ),
        ),
    ]
