from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_remove_banxa_coinbase_onramp_provider"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userpreferences",
            name="preferred_onramp_provider",
        ),
    ]
