from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_userprofile_residence_country"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="sumsub_review_answer",
            field=models.CharField(
                blank=True,
                choices=[("GREEN", "Approved"), ("RED", "Rejected"), ("YELLOW", "Retry")],
                max_length=50,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="sumsub_review_result",
            field=models.CharField(
                blank=True,
                choices=[("GREEN", "Approved"), ("RED", "Rejected"), ("YELLOW", "Retry")],
                max_length=50,
                null=True,
            ),
        ),
    ]
