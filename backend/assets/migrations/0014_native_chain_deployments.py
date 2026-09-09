from django.db import migrations


def seed_native_deployments(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    Deployment = apps.get_model("assets", "AssetChainDeployment")
    alias = schema_editor.connection.alias
    for symbol, decimals, chains in (("ETH", 18, ("ethereum", "base")), ("BTC", 8, ("bitcoin",))):
        asset = Asset.objects.using(alias).filter(symbol=symbol, asset_type="native_crypto").first()
        if asset is None:
            continue
        for chain in chains:
            Deployment.objects.using(alias).get_or_create(
                asset=asset,
                chain=chain,
                defaults={"decimals": decimals, "is_active": asset.is_active},
            )


class Migration(migrations.Migration):
    dependencies = [("assets", "0013_price_provenance")]
    operations = [migrations.RunPython(seed_native_deployments, migrations.RunPython.noop)]
