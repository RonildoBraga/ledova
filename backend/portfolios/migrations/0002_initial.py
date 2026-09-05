import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("assets", "0001_initial"),
        ("portfolios", "0001_initial"),
        ("users", "0001_initial"),
        ("wallets", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="portfolio",
            name="user_account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="portfolios", to="users.useraccount"
            ),
        ),
        migrations.AddField(
            model_name="portfolio",
            name="wallets",
            field=models.ManyToManyField(blank=True, related_name="portfolios", to="wallets.wallet"),
        ),
        migrations.AddField(
            model_name="assetallocation",
            name="portfolio",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="portfolios.portfolio"
            ),
        ),
        migrations.AddField(
            model_name="portfoliosnapshot",
            name="portfolio",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="snapshots", to="portfolios.portfolio"
            ),
        ),
        migrations.AddField(
            model_name="portfolio",
            name="template",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="portfolios.portfoliotemplate"
            ),
        ),
        migrations.AddField(
            model_name="targetassetallocation",
            name="asset",
            field=models.ForeignKey(
                help_text="Target asset for allocation", on_delete=django.db.models.deletion.CASCADE, to="assets.asset"
            ),
        ),
        migrations.AddField(
            model_name="targetassetallocation",
            name="template",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="allocations",
                to="portfolios.portfoliotemplate",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="assetallocation",
            unique_together={("portfolio", "asset")},
        ),
        migrations.AddIndex(
            model_name="portfoliosnapshot",
            index=models.Index(fields=["portfolio", "-snapshot_date"], name="portfolio_s_portfol_4f5098_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="targetassetallocation",
            unique_together={("template", "asset")},
        ),
    ]
