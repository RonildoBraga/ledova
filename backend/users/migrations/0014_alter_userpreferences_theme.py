from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0013_add_theme_to_user_preferences"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userpreferences",
            name="theme",
            field=models.CharField(choices=[("dark", "Dark"), ("light", "Light")], default="dark", max_length=10),
        ),
    ]
