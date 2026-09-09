from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wallets", "0010_durable_state_for_a_submitted_transaction")]

    operations = [
        migrations.AddField(
            model_name="wallet",
            name="verification_challenge_issued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
