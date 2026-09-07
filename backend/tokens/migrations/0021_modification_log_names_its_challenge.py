import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0020_shareissuance_identity_stamped_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ordermodificationlog",
            name="challenge",
            field=models.ForeignKey(
                blank=True,
                help_text="The signing challenge that authorized this modification, and the message it carried.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="modification_logs",
                to="tokens.signingchallenge",
            ),
        ),
        migrations.AlterField(
            model_name="ordermodificationlog",
            name="modification_message",
            field=models.TextField(
                blank=True,
                help_text=(
                    "The message that was signed, for rows written before modifications "
                    "were authorized by a challenge."
                ),
            ),
        ),
    ]
