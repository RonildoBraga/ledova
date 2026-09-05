from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("whitelist", "0002_whitelistentry_treasury_addresses"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="whitelistentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("wallet__isnull", True)),
                fields=("address",),
                name="whitelist_entry_unique_treasury_address",
            ),
        ),
    ]
