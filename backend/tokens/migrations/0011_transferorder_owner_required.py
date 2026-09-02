import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tokens", "0010_transferorder_bind_legacy_orders"),
        ("users", "0015_add_display_currency_preference"),
        ("wallets", "0004_wallet_is_operator"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="transferorder",
            name="transfer_order_ownership_pair",
        ),
        migrations.AlterField(
            model_name="transferorder",
            name="wallet",
            field=models.ForeignKey(
                help_text="Verified tenant wallet that owns this order.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="transfer_orders",
                to="wallets.wallet",
            ),
        ),
        migrations.AlterField(
            model_name="transferorder",
            name="owner_account",
            field=models.ForeignKey(
                help_text="Immutable tenant snapshot for this order.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="transfer_orders",
                to="users.useraccount",
            ),
        ),
    ]
