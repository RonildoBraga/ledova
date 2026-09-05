import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def require_every_company_to_have_an_owner(apps, schema_editor):
    Company = apps.get_model("companies", "Company")
    orphans = list(Company.objects.filter(owner__isnull=True).values_list("acn", flat=True))
    if orphans:
        raise RuntimeError(f"Companies without an owner must be assigned first: {', '.join(orphans)}")


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(require_every_company_to_have_an_owner, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="company",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_companies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
