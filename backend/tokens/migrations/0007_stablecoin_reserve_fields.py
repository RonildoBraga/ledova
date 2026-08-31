from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0006_rename_tokens_stab_status_4c5fd9_idx_tokens_mint_status_99ebab_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="stablecoin",
            name="reserve_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=20, null=True),
        ),
        migrations.AddField(
            model_name="stablecoin",
            name="reserve_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
