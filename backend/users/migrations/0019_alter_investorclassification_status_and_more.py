import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0018_investor_classification"),
    ]

    operations = [
        migrations.AlterField(
            model_name="investorclassification",
            name="status",
            field=models.CharField(
                choices=[
                    ("submitted", "Submitted"),
                    ("verified", "Verified"),
                    ("rejected", "Rejected"),
                    ("revoked", "Revoked"),
                    ("withdrawn", "Withdrawn"),
                ],
                default="submitted",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="investorclassification",
            name="user_account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="investor_classifications",
                to="users.useraccount",
            ),
        ),
    ]
