from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("whitelist", "0003_whitelistentry_unique_treasury_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="whitelistentry",
            name="failure_reconciled_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
