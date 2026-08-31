from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0010_remove_userpreferences_preferred_onramp_provider"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Widget",
        ),
    ]
