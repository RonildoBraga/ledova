from django.db import migrations, models
from django.db.models.functions import Lower

DUPLICATE_TX_HASHES = (
    "One on-chain transfer cannot fund two subscriptions, and these already differ only in case: {rows}. "
    "Resolve them before applying this migration."
)


def fold_tx_hashes_to_lower_case(apps, schema_editor):
    Subscription = apps.get_model("offerings", "Subscription")
    rows = Subscription.objects.exclude(payment_tx_hash="")
    seen = {}
    for row_uuid, tx_hash in rows.values_list("uuid", "payment_tx_hash"):
        seen.setdefault(tx_hash.lower(), []).append(str(row_uuid))
    clashes = [uuids for uuids in seen.values() if len(uuids) > 1]
    if clashes:
        raise RuntimeError(DUPLICATE_TX_HASHES.format(rows=clashes))
    rows.update(payment_tx_hash=Lower("payment_tx_hash"))


class Migration(migrations.Migration):

    dependencies = [
        ("offerings", "0002_subscription"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="subscription",
            name="subscription_payment_tx_hash_unique",
        ),
        migrations.RunPython(fold_tx_hashes_to_lower_case, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                Lower("payment_tx_hash"),
                condition=models.Q(("payment_tx_hash", ""), _negated=True),
                name="subscription_payment_tx_hash_unique",
            ),
        ),
    ]
