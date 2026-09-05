from django.conf import settings
from django.db import migrations

from shared.constants import BLOCKCHAIN_BASE, BLOCKCHAIN_ETHEREUM

AUDY = "AUDY"


def _configured_address() -> str:
    return (getattr(settings, "STABLECOIN_CONTRACT_ADDRESS", "") or "").strip()


def _audy_deployments(apps):
    Asset = apps.get_model("assets", "Asset")
    AssetChainDeployment = apps.get_model("assets", "AssetChainDeployment")
    asset = Asset.objects.filter(symbol=AUDY).first()
    if asset is None:
        return None
    return AssetChainDeployment.objects.filter(asset=asset)


def move_audy_to_base(apps, schema_editor):
    address = _configured_address()
    if not address:
        return
    deployments = _audy_deployments(apps)
    if deployments is None or deployments.filter(chain=BLOCKCHAIN_BASE).exists():
        return
    deployment = deployments.filter(chain=BLOCKCHAIN_ETHEREUM).first()
    if deployment is None:
        return
    deployment.chain = BLOCKCHAIN_BASE
    deployment.contract_address = address
    deployment.save(update_fields=["chain", "contract_address"])


def move_audy_to_ethereum(apps, schema_editor):
    address = _configured_address()
    if not address:
        return
    deployments = _audy_deployments(apps)
    if deployments is None or deployments.filter(chain=BLOCKCHAIN_ETHEREUM).exists():
        return
    deployment = deployments.filter(chain=BLOCKCHAIN_BASE, contract_address__iexact=address).first()
    if deployment is None:
        return
    deployment.chain = BLOCKCHAIN_ETHEREUM
    deployment.contract_address = None
    deployment.save(update_fields=["chain", "contract_address"])


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0011_add_exchange_rate_model"),
    ]

    operations = [
        migrations.RunPython(move_audy_to_base, move_audy_to_ethereum),
    ]
