from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_delete_widget"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccount",
            name="role",
            field=models.CharField(
                choices=[("investor", "Investor"), ("company", "Company"), ("both", "Both")],
                default="investor",
                max_length=10,
            ),
        ),
    ]
