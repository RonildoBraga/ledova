import logging
from uuid import UUID

from django.db import migrations

from shared.constants import BLOCKCHAIN_BASE

logger = logging.getLogger(__name__)

STABLECOIN = "stablecoin"
SYMBOL_MAX_LENGTH = 10
GRANT_TABLE = "tokens_stablecoin_fold_grant"
ADDRESS_CONFLICT = (
    "stablecoin {symbol} carries {coin_address} but {asset_symbol} on {chain} already carries " "{deployment_address}"
)
ADDRESS_CONFLICTS = (
    "The fold would point a settlement path at a contract the stablecoin row does not name: {conflicts}. "
    "Reconcile the addresses before applying this migration; nothing has been written."
)
ORPHANED_SWAP_ORDERS = "{count} swap orders have no settlement asset after the fold."
NOT_RESTORABLE = "{symbol} cannot be represented as a stablecoin row; its foreign keys were left null."
GRANTS_NOT_RECORDED = (
    "No record of what the fold added to Operator.supported_settlement_assets; the list is left as it stands."
)
FK_COLUMNS = (
    ("MintRequest", "settlement_asset", "stablecoin"),
    ("SwapOrder", "payment_asset", "payment_token"),
    ("TransferOrder", "payment_asset", "payment_token"),
)


def _operator(apps):
    return apps.get_model("operators", "Operator").objects.first()


def _settlement_chain(apps) -> str:
    operator = _operator(apps)
    return operator.receiving_wallet_chain if operator else BLOCKCHAIN_BASE


def _matching_asset(apps, coin, chain):
    Asset = apps.get_model("assets", "Asset")
    AssetChainDeployment = apps.get_model("assets", "AssetChainDeployment")

    asset = Asset.objects.filter(symbol__iexact=coin.symbol).first()
    if asset is not None:
        return asset

    deployment = (
        AssetChainDeployment.objects.select_related("asset")
        .filter(chain=chain, contract_address__iexact=coin.contract_address)
        .first()
    )
    if deployment is not None:
        return deployment.asset

    return Asset.objects.create(
        symbol=coin.symbol.upper(),
        name=coin.name,
        asset_type=STABLECOIN,
        decimals=coin.decimals,
        is_active=coin.is_active,
        is_verified=True,
    )


def _conflict(coin, asset, chain, deployment) -> str:
    return ADDRESS_CONFLICT.format(
        symbol=coin.symbol,
        coin_address=coin.contract_address,
        asset_symbol=asset.symbol,
        chain=chain,
        deployment_address=deployment.contract_address,
    )


def _upsert_deployment(apps, asset, coin, chain):
    AssetChainDeployment = apps.get_model("assets", "AssetChainDeployment")

    deployment = AssetChainDeployment.objects.filter(asset=asset, chain=chain).first()
    if deployment is None:
        clash = (
            AssetChainDeployment.objects.select_related("asset")
            .filter(chain=chain, contract_address__iexact=coin.contract_address)
            .first()
        )
        if clash is not None:
            return _conflict(coin, clash.asset, chain, clash)
        AssetChainDeployment.objects.create(
            asset=asset,
            chain=chain,
            contract_address=coin.contract_address,
            decimals=coin.decimals,
            is_active=coin.is_active,
        )
        return None

    if deployment.contract_address and deployment.contract_address.lower() != coin.contract_address.lower():
        return _conflict(coin, asset, chain, deployment)

    deployment.contract_address = coin.contract_address
    deployment.save(update_fields=["contract_address"])
    return None


def _record_grants(schema_editor, asset_ids):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {GRANT_TABLE}")
        cursor.execute(f"CREATE TABLE {GRANT_TABLE} (asset_id varchar(36) PRIMARY KEY)")
        for asset_id in sorted(str(asset_id) for asset_id in asset_ids):
            cursor.execute(f"INSERT INTO {GRANT_TABLE} (asset_id) VALUES (%s)", [asset_id])


def _granted_ids(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        if GRANT_TABLE not in schema_editor.connection.introspection.table_names(cursor):
            logger.warning(GRANTS_NOT_RECORDED)
            return set()
        cursor.execute(f"SELECT asset_id FROM {GRANT_TABLE}")
        return {UUID(row[0]) for row in cursor.fetchall()}


def _drop_grants(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {GRANT_TABLE}")


def _support(apps, schema_editor, asset_ids):
    operator = _operator(apps)
    granted = set()
    if operator is not None:
        candidates = set(asset_ids)
        if operator.issued_stablecoin_id:
            candidates.add(operator.issued_stablecoin_id)
        granted = candidates - set(operator.supported_settlement_assets.values_list("pk", flat=True))
        if granted:
            operator.supported_settlement_assets.add(*granted)
    _record_grants(schema_editor, granted)


def _withdraw_support(apps, asset_ids):
    operator = _operator(apps)
    if operator is None or not asset_ids:
        return
    operator.supported_settlement_assets.remove(*asset_ids)


def _referenced_asset_ids(apps):
    asset_ids = set()
    for model_name, source, _ in FK_COLUMNS:
        model = apps.get_model("tokens", model_name)
        asset_ids.update(model.objects.exclude(**{f"{source}__isnull": True}).values_list(f"{source}_id", flat=True))
    return asset_ids


def _restored_address(apps, asset, chain) -> str:
    deployments = (
        apps.get_model("assets", "AssetChainDeployment")
        .objects.filter(asset=asset)
        .exclude(contract_address__isnull=True)
        .exclude(contract_address="")
    )
    deployment = deployments.filter(chain=chain).first() or deployments.first()
    return deployment.contract_address if deployment else ""


def _restored_coin(apps, asset, chain):
    Stablecoin = apps.get_model("tokens", "Stablecoin")

    coin = Stablecoin.objects.filter(symbol__iexact=asset.symbol).first()
    if coin is not None:
        return coin

    address = _restored_address(apps, asset, chain)
    if not address or len(asset.symbol) > SYMBOL_MAX_LENGTH:
        logger.warning(NOT_RESTORABLE.format(symbol=asset.symbol))
        return None
    if Stablecoin.objects.filter(contract_address__iexact=address).exists():
        return Stablecoin.objects.filter(contract_address__iexact=address).first()

    return Stablecoin.objects.create(
        name=asset.name,
        symbol=asset.symbol,
        contract_address=address,
        decimals=asset.decimals,
        is_active=asset.is_active,
    )


def fold_stablecoins(apps, schema_editor):
    Stablecoin = apps.get_model("tokens", "Stablecoin")
    MintRequest = apps.get_model("tokens", "MintRequest")
    SwapOrder = apps.get_model("tokens", "SwapOrder")
    TransferOrder = apps.get_model("tokens", "TransferOrder")

    chain = _settlement_chain(apps)
    folded = set()
    conflicts = []

    for coin in Stablecoin.objects.all():
        asset = _matching_asset(apps, coin, chain)
        conflict = _upsert_deployment(apps, asset, coin, chain)
        if conflict:
            conflicts.append(conflict)
            continue
        MintRequest.objects.filter(stablecoin=coin).update(settlement_asset=asset)
        SwapOrder.objects.filter(payment_token=coin).update(payment_asset=asset)
        TransferOrder.objects.filter(payment_token=coin).update(payment_asset=asset)
        folded.add(asset.pk)

    if conflicts:
        raise RuntimeError(ADDRESS_CONFLICTS.format(conflicts="; ".join(sorted(conflicts))))

    orphans = SwapOrder.objects.filter(payment_asset__isnull=True).count()
    if orphans:
        raise RuntimeError(ORPHANED_SWAP_ORDERS.format(count=orphans))

    _support(apps, schema_editor, folded)


def unfold_stablecoins(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")

    chain = _settlement_chain(apps)
    granted = _granted_ids(schema_editor)
    coins = {}
    for asset in Asset.objects.filter(pk__in=granted | _referenced_asset_ids(apps)):
        coin = _restored_coin(apps, asset, chain)
        if coin is not None:
            coins[asset.pk] = coin

    for model_name, source, target in FK_COLUMNS:
        model = apps.get_model("tokens", model_name)
        for asset_id, coin in coins.items():
            model.objects.filter(**{source: asset_id}).update(**{target: coin, source: None})
        model.objects.exclude(**{f"{source}__isnull": True}).update(**{source: None})

    _withdraw_support(apps, granted)
    _drop_grants(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("operators", "0001_initial"),
        ("tokens", "0014_settlement_asset_columns"),
    ]

    operations = [
        migrations.RunPython(fold_stablecoins, unfold_stablecoins),
    ]
