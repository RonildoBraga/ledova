from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portfolios", "0003_remove_portfolio_template_and_target_asset_allocation"),
    ]

    operations = [
        migrations.DeleteModel(
            name="AssetAllocation",
        ),
    ]
