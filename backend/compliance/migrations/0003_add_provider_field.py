from django.db import migrations, models


def populate_provider_fields(apps, schema_editor):
    TransactionScreening = apps.get_model("compliance", "TransactionScreening")
    for screening in TransactionScreening.objects.all().iterator():
        screening.provider = "sumsub"
        screening.provider_transaction_id = screening.sumsub_transaction_id
        screening.save(update_fields=["provider", "provider_transaction_id"])


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="transactionscreening",
            name="provider",
            field=models.CharField(
                default="sumsub",
                help_text="KYC/KYT provider used for this screening",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="transactionscreening",
            name="provider_transaction_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Provider-agnostic transaction ID",
                max_length=100,
                null=True,
            ),
        ),
        migrations.RunPython(populate_provider_fields, reverse_populate),
    ]
