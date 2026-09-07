from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0019_signing_challenge"),
    ]

    operations = [
        migrations.AddField(
            model_name="shareissuance",
            name="identity_stamped_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the recipient name and address were stamped, or null if they never were",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="shareissuance",
            name="recipient_residential_address",
            field=models.TextField(
                blank=True, help_text="The holder's residential address as it stood when the shares were allotted"
            ),
        ),
        migrations.AlterField(
            model_name="shareissuance",
            name="recipient_name",
            field=models.CharField(
                blank=True, help_text="The holder's name as it stood when the shares were allotted", max_length=255
            ),
        ),
    ]
