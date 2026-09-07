from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0021_modification_log_names_its_challenge"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="swaporder",
            constraint=models.UniqueConstraint(fields=("nonce",), name="unique_swap_nonce"),
        ),
    ]
