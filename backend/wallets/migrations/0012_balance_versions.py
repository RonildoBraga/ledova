import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wallets", "0011_wallet_verification_challenge_issued_at")]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="balance_reconciliation_token",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="holding", name="balance_version", field=models.UUIDField(default=uuid.uuid4, editable=False)
        ),
        migrations.AddField(
            model_name="holding", name="sync_version", field=models.UUIDField(default=uuid.uuid4, editable=False)
        ),
        migrations.AddField(
            model_name="transaction",
            name="deducted_amount_sync_version",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="transaction",
            name="deducted_fee_sync_version",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
    ]
