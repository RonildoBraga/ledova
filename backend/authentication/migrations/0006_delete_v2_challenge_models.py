from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0005_auth_del_superseded_proof_shapes"),
    ]

    operations = [
        migrations.DeleteModel(name="AuthenticationChallengeDelivery"),
        migrations.DeleteModel(name="AuthenticationChallenge"),
    ]
