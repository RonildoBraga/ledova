from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_useraccount_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreferences",
            name="theme",
            field=models.CharField(
                choices=[("dark", "Dark"), ("light", "Light")],
                default="dark",
                help_text="User's preferred color theme",
                max_length=10,
            ),
        ),
    ]
