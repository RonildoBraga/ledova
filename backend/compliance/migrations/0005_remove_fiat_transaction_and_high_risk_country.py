from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0004_remove_sumsub_transaction_id"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="compliancealert",
            name="fiat_transaction",
        ),
        migrations.RemoveField(
            model_name="customerriskassessment",
            name="high_risk_country",
        ),
    ]
