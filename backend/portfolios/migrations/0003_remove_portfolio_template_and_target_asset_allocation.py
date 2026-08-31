# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portfolios", "0002_initial"),
    ]

    operations = [
        # Remove the FK from Portfolio to PortfolioTemplate first
        migrations.RemoveField(
            model_name="portfolio",
            name="template",
        ),
        # Drop TargetAssetAllocation (depends on PortfolioTemplate)
        migrations.DeleteModel(
            name="TargetAssetAllocation",
        ),
        # Drop PortfolioTemplate
        migrations.DeleteModel(
            name="PortfolioTemplate",
        ),
    ]
