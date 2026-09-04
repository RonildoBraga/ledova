from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("blockchain", "0002_alter_blockchaintransaction_tx_type"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ContractDeployment",
        ),
    ]
