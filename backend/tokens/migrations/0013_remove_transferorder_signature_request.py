from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0012_reviewable_request"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="transferorder",
            name="signature_request",
        ),
    ]
