from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portfolios", "0002_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="portfolio",
            name="template",
        ),
        migrations.DeleteModel(
            name="TargetAssetAllocation",
        ),
        migrations.DeleteModel(
            name="PortfolioTemplate",
        ),
    ]
