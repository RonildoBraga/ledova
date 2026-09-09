from django.db import migrations, models
from django.db.models.functions import Lower

EVM_CHAINS = ["arbitrum", "avalanche", "base", "ethereum", "optimism", "polygon"]


def refuse_ambiguous_existing_identities(apps, schema_editor):
    wallets = apps.get_model("wallets", "Wallet").objects.using(schema_editor.connection.alias)
    duplicates = (
        wallets.filter(chain__in=EVM_CHAINS)
        .annotate(network_address=Lower("address"))
        .values("user_account_id", "chain", "network_address")
        .annotate(total=models.Count("pk"))
        .filter(total__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError(
            "Duplicate EVM wallet identities exist within one account and network. "
            "Resolve those records while preserving their financial references before retrying wallets.0014. "
            "This migration has not merged or deleted any wallet."
        )


class Migration(migrations.Migration):
    dependencies = [("wallets", "0013_signing_preference")]
    operations = [
        migrations.RunPython(refuse_ambiguous_existing_identities, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(name="wallet", unique_together=set()),
        migrations.AddConstraint(
            model_name="wallet",
            constraint=models.UniqueConstraint(
                fields=("user_account", "chain", "address"), name="unique_wallet_network_address"
            ),
        ),
        migrations.AddConstraint(
            model_name="wallet",
            constraint=models.UniqueConstraint(
                Lower("address"),
                models.F("user_account"),
                models.F("chain"),
                condition=models.Q(chain__in=EVM_CHAINS),
                name="unique_evm_wallet_network_address",
            ),
        ),
    ]
