from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0007_delete_authsession_refreshcredential"),
    ]

    operations = [
        migrations.DeleteModel(
            name="UserToken",
        ),
    ]
