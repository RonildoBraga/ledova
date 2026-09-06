from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0004_company_additional_info_response"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="is_open_to_investors",
            field=models.BooleanField(
                default=False, help_text="Show this company's share classes in the investor directory."
            ),
        ),
    ]
