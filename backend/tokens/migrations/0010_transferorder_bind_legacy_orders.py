from django.db import migrations
from django.db.models import Q

EVM_CHAINS = ("ethereum", "base")


def bind_or_delete_unbound_orders(apps, schema_editor):
    TransferOrder = apps.get_model("tokens", "TransferOrder")
    Wallet = apps.get_model("wallets", "Wallet")

    for order in TransferOrder.objects.filter(Q(wallet__isnull=True) | Q(owner_account__isnull=True)):
        wallets = list(
            Wallet.objects.filter(
                address__iexact=order.wallet_address,
                verification_status="VERIFIED",
                chain__in=EVM_CHAINS,
            )[:2]
        )
        if len(wallets) == 1:
            order.wallet = wallets[0]
            order.owner_account_id = wallets[0].user_account_id
            order.save(update_fields=["wallet", "owner_account"])
        else:
            order.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tokens", "0009_transferorder_ownership"),
        ("users", "0015_add_display_currency_preference"),
        ("wallets", "0004_wallet_is_operator"),
    ]

    operations = [
        migrations.RunPython(bind_or_delete_unbound_orders, migrations.RunPython.noop),
    ]
