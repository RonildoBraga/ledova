from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0003_add_provider_field"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="transactionscreening",
            name="sumsub_transaction_id",
        ),
        migrations.AlterField(
            model_name="transactionscreening",
            name="provider",
            field=models.CharField(default="kycaid", help_text="KYT provider used for this screening", max_length=20),
        ),
        migrations.AlterField(
            model_name="transactionscreening",
            name="provider_transaction_id",
            field=models.CharField(
                blank=True, db_index=True, help_text="Provider transaction/request ID", max_length=100, null=True
            ),
        ),
        migrations.AlterField(
            model_name="transactionscreening",
            name="raw_response",
            field=models.JSONField(default=dict, help_text="Complete response from provider API for audit purposes"),
        ),
        migrations.AlterField(
            model_name="transactionscreening",
            name="submitted_at",
            field=models.DateTimeField(auto_now_add=True, help_text="When the screening was submitted"),
        ),
    ]
