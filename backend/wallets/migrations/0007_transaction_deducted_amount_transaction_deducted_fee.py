from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0006_delete_fiattransaction_drop_unread_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="deducted_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=18,
                help_text="What the optimistic deduction actually took from the asset's holding, after the floor at zero. Carries the fee as well when the asset is the chain's native coin. Null for rows written before the deduction was recorded.",
                max_digits=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="deducted_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=18,
                help_text="What the optimistic deduction actually took from the native holding, after the floor at zero. Null when the asset is itself native, and for rows written before the deduction was recorded.",
                max_digits=30,
                null=True,
            ),
        ),
    ]
