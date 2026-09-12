from django.db import migrations, models


def require_distinct_identities(apps, schema_editor):
    submissions = apps.get_model("wallets", "WalletSubmission").objects.using(schema_editor.connection.alias)
    for fields in (("chain_id", "tx_hash"), ("chain_id", "sender_address", "nonce")):
        if submissions.values(*fields).annotate(records=models.Count("pk")).filter(records__gt=1).exists():
            raise RuntimeError(
                "Existing EVM submissions share chain identities; retain these rows and reconcile ownership before retrying."
            )


class Migration(migrations.Migration):
    dependencies = [("wallets", "0017_bitcoin_submission")]

    operations = [
        migrations.RunPython(require_distinct_identities, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="walletsubmission",
            constraint=models.UniqueConstraint(fields=("chain_id", "tx_hash"), name="unique_submission_chain_hash"),
        ),
        migrations.AddConstraint(
            model_name="walletsubmission",
            constraint=models.UniqueConstraint(
                fields=("chain_id", "sender_address", "nonce"), name="unique_submission_sender_nonce"
            ),
        ),
    ]
