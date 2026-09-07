from django.db import migrations, models

import companies.validators


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0006_company_document_private_storage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="company",
            name="abn",
            field=models.CharField(blank=True, max_length=14, validators=[companies.validators.validate_abn]),
        ),
        migrations.AlterField(
            model_name="company",
            name="acn",
            field=models.CharField(max_length=11, unique=True, validators=[companies.validators.validate_acn]),
        ),
    ]
