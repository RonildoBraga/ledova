from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portfolios", "0004_delete_assetallocation"),
    ]

    operations = [
        migrations.DeleteModel(
            name="PortfolioSnapshot",
        ),
    ]
