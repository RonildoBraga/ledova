from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0012_balance_versions"),
    ]

    operations = [
        migrations.RenameField(
            model_name="wallet",
            old_name="wallet_type",
            new_name="signing_preference",
        ),
        migrations.AlterField(
            model_name="wallet",
            name="signing_preference",
            field=models.CharField(
                blank=True,
                choices=[("hardware", "Hardware"), ("software", "Software")],
                help_text="Self-declared signing preference. It does not attest custody or hardware use.",
                max_length=16,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="wallet",
            name="master_fingerprint",
            field=models.CharField(
                blank=True,
                help_text="Client-provided key fingerprint (8-char hex); not hardware attestation",
                max_length=8,
                null=True,
            ),
        ),
    ]
