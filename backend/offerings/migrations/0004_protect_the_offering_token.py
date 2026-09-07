import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("offerings", "0003_subscription_tx_hash_case_insensitive"),
        ("tokens", "0017_share_token_chain"),
    ]

    operations = [
        migrations.AlterField(
            model_name="offering",
            name="token",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="offerings", to="tokens.sharetoken"
            ),
        ),
    ]
