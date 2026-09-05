import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0015_fold_stablecoin_into_asset"),
    ]

    operations = [
        migrations.AlterField(
            model_name="swaporder",
            name="payment_asset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="swap_orders",
                to="assets.asset",
            ),
        ),
        migrations.RemoveField(
            model_name="mintrequest",
            name="stablecoin",
        ),
        migrations.RemoveField(
            model_name="swaporder",
            name="payment_token",
        ),
        migrations.RemoveField(
            model_name="transferorder",
            name="payment_token",
        ),
        migrations.DeleteModel(
            name="Stablecoin",
        ),
    ]
