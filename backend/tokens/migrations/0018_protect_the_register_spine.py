import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0006_company_document_private_storage"),
        ("tokens", "0017_share_token_chain"),
    ]

    operations = [
        migrations.AlterField(
            model_name="capitalincreaserequest",
            name="token",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="capital_increase_requests",
                to="tokens.sharetoken",
            ),
        ),
        migrations.AlterField(
            model_name="shareissuance",
            name="token",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="issuances", to="tokens.sharetoken"
            ),
        ),
        migrations.AlterField(
            model_name="shareissuancerequest",
            name="token",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="issuance_requests", to="tokens.sharetoken"
            ),
        ),
        migrations.AlterField(
            model_name="sharetoken",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="tokens", to="companies.company"
            ),
        ),
        migrations.AlterField(
            model_name="transferorder",
            name="token",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="transfer_orders", to="tokens.sharetoken"
            ),
        ),
    ]
