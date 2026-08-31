from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0004_seed_ausg_yield_token"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="TokenIssuance",
            new_name="ShareIssuance",
        ),
        migrations.AlterModelOptions(
            name="shareissuance",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Share Issuance",
                "verbose_name_plural": "Share Issuances",
            },
        ),
    ]
