from django.db import migrations, models

from shared.constants import BLOCKCHAIN_BASE


def set_chain_of_deployed_tokens(apps, schema_editor):
    ShareToken = apps.get_model("tokens", "ShareToken")
    ShareToken.objects.exclude(contract_address__isnull=True).exclude(contract_address="").update(chain=BLOCKCHAIN_BASE)


def clear_chain(apps, schema_editor):
    ShareToken = apps.get_model("tokens", "ShareToken")
    ShareToken.objects.update(chain=None)


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0016_drop_stablecoin"),
    ]

    operations = [
        migrations.AddField(
            model_name="sharetoken",
            name="chain",
            field=models.CharField(
                blank=True,
                help_text="Blockchain the contract was deployed to (null until deployment confirms)",
                max_length=32,
                null=True,
            ),
        ),
        migrations.RunPython(set_chain_of_deployed_tokens, clear_chain),
    ]
