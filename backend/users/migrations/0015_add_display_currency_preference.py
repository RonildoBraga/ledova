from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0014_alter_userpreferences_theme"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreferences",
            name="display_currency",
            field=models.CharField(
                choices=[("AUD", "Australian Dollar"), ("USD", "US Dollar")],
                default="AUD",
                help_text="Currency used for displaying prices and values",
                max_length=8,
            ),
        ),
    ]
