from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_remove_userprofile_investor_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userpreferences",
            name="preferred_onramp_provider",
            field=models.CharField(
                blank=True,
                choices=[("transak", "Transak"), ("banxa", "Banxa"), ("coinbase", "Coinbase")],
                help_text="User's preferred fiat on-ramp provider for buying crypto",
                max_length=20,
                null=True,
            ),
        ),
    ]
