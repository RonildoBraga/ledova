from django.db import migrations


def create_ausg_yield_token(apps, schema_editor):

    pass


def reverse_ausg(apps, schema_editor):
    YieldToken = apps.get_model("tokens", "YieldToken")
    YieldToken.objects.filter(symbol="AUSG").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0003_unify_mint_request"),
        ("assets", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_ausg_yield_token, reverse_ausg),
    ]
