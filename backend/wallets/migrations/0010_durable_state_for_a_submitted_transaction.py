from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0009_trigger_follows_and_refuses"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="block_hash",
            field=models.CharField(
                blank=True,
                help_text="Hash of the block this landed in, so a reorganisation that replaced it can be seen",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="nonce",
            field=models.BigIntegerField(
                blank=True,
                db_index=True,
                help_text="Sender's nonce for this broadcast, which is what ties a replacement to what it replaced",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="replaced_by_tx_hash",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="The hash that landed instead of this one, for a speed-up or a cancellation",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("failed", "Failed"),
                    ("reorged", "Confirmed, then dropped by a chain reorganisation"),
                    ("replaced", "Replaced by another transaction that landed instead"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
