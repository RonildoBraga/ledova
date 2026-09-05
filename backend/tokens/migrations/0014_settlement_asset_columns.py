import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0012_audy_base_deployment"),
        ("tokens", "0013_remove_transferorder_signature_request"),
    ]

    operations = [
        migrations.AlterField(
            model_name="swaporder",
            name="payment_token",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="swap_orders",
                to="tokens.stablecoin",
            ),
        ),
        migrations.AddField(
            model_name="mintrequest",
            name="settlement_asset",
            field=models.ForeignKey(
                blank=True,
                help_text="The settlement asset being minted (if applicable)",
                limit_choices_to={"asset_type": "stablecoin"},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mint_requests",
                to="assets.asset",
            ),
        ),
        migrations.AddField(
            model_name="swaporder",
            name="payment_asset",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="swap_orders",
                to="assets.asset",
            ),
        ),
        migrations.AddField(
            model_name="transferorder",
            name="payment_asset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transfer_orders",
                to="assets.asset",
            ),
        ),
    ]
