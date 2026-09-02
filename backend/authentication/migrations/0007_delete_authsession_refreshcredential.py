from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0006_delete_v2_challenge_models"),
    ]

    operations = [
        migrations.DeleteModel(name="RefreshCredential"),
        migrations.DeleteModel(name="AuthSession"),
    ]
