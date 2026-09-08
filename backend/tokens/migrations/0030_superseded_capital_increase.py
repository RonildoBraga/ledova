from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0026_one_capital_increase_in_flight"),
    ]

    operations = [
        migrations.AlterField(
            model_name="capitalincreaserequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("under_review", "Under Review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("executing", "Executing"),
                    ("executed", "Executed"),
                    ("failed", "Failed"),
                    ("superseded", "Superseded"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="shareissuancerequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("under_review", "Under Review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("executing", "Executing"),
                    ("executed", "Executed"),
                    ("failed", "Failed"),
                    ("superseded", "Superseded"),
                ],
                default="submitted",
                max_length=20,
            ),
        ),
    ]
