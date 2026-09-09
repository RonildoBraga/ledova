from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("tokens", "0033_the_fold_records_where_it_reached")]

    operations = [
        migrations.AlterField(
            model_name="shareissuance",
            name="tx_hash",
            field=models.CharField(
                blank=True,
                help_text="Fixed mint transaction hash, recorded before submission for journaled issuances",
                max_length=66,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="shareissuance",
            name="mint_journal",
            field=models.JSONField(
                blank=True,
                editable=False,
                help_text="Signed mint attempts retained for replay; null identifies a legacy issuance without a journal",
                null=True,
            ),
        ),
    ]
