import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blockchain", "0001_initial"),
        ("tokens", "0002_yield_token_and_nav"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name="StablecoinMintRequest",
            new_name="MintRequest",
        ),
        migrations.AlterField(
            model_name="mintrequest",
            name="stablecoin",
            field=models.ForeignKey(
                blank=True,
                help_text="The stablecoin being minted (if applicable)",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mint_requests",
                to="tokens.stablecoin",
            ),
        ),
        migrations.AddField(
            model_name="mintrequest",
            name="yield_token",
            field=models.ForeignKey(
                blank=True,
                help_text="The yield token being minted (if applicable)",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mint_requests",
                to="tokens.yieldtoken",
            ),
        ),
        migrations.AlterField(
            model_name="mintrequest",
            name="amount",
            field=models.BigIntegerField(
                help_text="Amount to mint in raw units (e.g., 10000 = $100.00 for 2-decimal stablecoin, 1000000 = 1.000000 for 6-decimal yield token)",
            ),
        ),
        migrations.AlterField(
            model_name="mintrequest",
            name="requested_by",
            field=models.ForeignKey(
                help_text="Staff member who created this request",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mint_requests_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="mintrequest",
            name="executed_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Staff member who executed this request",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mint_requests_executed",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="mintrequest",
            name="transaction",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mint_requests",
                to="blockchain.blockchaintransaction",
            ),
        ),
        migrations.AlterField(
            model_name="mintrequest",
            name="deposit_reference",
            field=models.CharField(
                help_text="Synthetic scenario reference or test case ID",
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name="mintrequest",
            name="deposit_date",
            field=models.DateField(
                help_text="Date assigned to the synthetic scenario",
            ),
        ),
        migrations.AlterModelOptions(
            name="mintrequest",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Mint Request",
                "verbose_name_plural": "Mint Requests",
            },
        ),
    ]
