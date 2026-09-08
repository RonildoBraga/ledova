from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0027_former_holders"),
    ]

    operations = [
        migrations.AddField(
            model_name="sharetoken",
            name="former_holders_block",
            field=models.BigIntegerField(
                blank=True,
                help_text="The block the former-members fold last read up to, which the export reports beside its date",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="sharetoken",
            name="former_holders_folded_at",
            field=models.DateTimeField(
                blank=True, help_text="When the former-members fold last succeeded for this share class", null=True
            ),
        ),
    ]
