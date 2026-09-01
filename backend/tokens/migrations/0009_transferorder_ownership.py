import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tokens", "0008_share_issuance_request"),
        ("users", "0015_add_display_currency_preference"),
        ("wallets", "0004_wallet_is_operator"),
    ]

    operations = [
        migrations.AddField(
            model_name="transferorder",
            name="wallet",
            field=models.ForeignKey(
                blank=True,
                help_text="Verified tenant wallet that owns this order. Legacy unbound orders fail closed.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="transfer_orders",
                to="wallets.wallet",
            ),
        ),
        migrations.AddField(
            model_name="transferorder",
            name="owner_account",
            field=models.ForeignKey(
                blank=True,
                help_text="Immutable tenant snapshot for this order. Legacy unbound orders fail closed.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="transfer_orders",
                to="users.useraccount",
            ),
        ),
        migrations.AddConstraint(
            model_name="transferorder",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(owner_account__isnull=True, wallet__isnull=True)
                    | models.Q(owner_account__isnull=False, wallet__isnull=False)
                ),
                name="transfer_order_ownership_pair",
            ),
        ),
    ]
