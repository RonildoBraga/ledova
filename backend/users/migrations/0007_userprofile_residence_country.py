import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0001_initial"),
        ("users", "0006_populate_kyc_provider_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="residence_country",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="residents",
                to="shared.country",
            ),
        ),
    ]
