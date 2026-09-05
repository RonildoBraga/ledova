from django.db import migrations

MULTI_CHAIN_TOKENS = {}


def populate_deployments(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    AssetChainDeployment = apps.get_model("assets", "AssetChainDeployment")

    for asset in Asset.objects.filter(chain__isnull=False).exclude(chain=""):
        if asset.symbol in MULTI_CHAIN_TOKENS:
            for dep in MULTI_CHAIN_TOKENS[asset.symbol]:
                AssetChainDeployment.objects.get_or_create(
                    asset=asset,
                    chain=dep["chain"],
                    defaults={
                        "contract_address": dep["contract"],
                        "decimals": dep["decimals"],
                        "is_active": asset.is_active,
                    },
                )
        else:
            AssetChainDeployment.objects.get_or_create(
                asset=asset,
                chain=asset.chain,
                defaults={
                    "contract_address": asset.contract_address,
                    "decimals": asset.decimals,
                    "is_active": asset.is_active,
                },
            )


def reverse_deployments(apps, schema_editor):
    AssetChainDeployment = apps.get_model("assets", "AssetChainDeployment")
    AssetChainDeployment.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0005_add_asset_chain_deployment"),
    ]

    operations = [
        migrations.RunPython(populate_deployments, reverse_deployments),
    ]
