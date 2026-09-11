from collections.abc import Mapping
from decimal import Decimal, localcontext
from uuid import uuid4

from django.utils import timezone

from assets.models import Asset, AssetChainDeployment, AssetType
from assets.services.identity import native_asset_for_chain
from integrations.blockchain import get_blockchain_client
from integrations.blockchain.receipts import nonnegative_integer, normalized_hash
from shared.db import atomic
from users.models import UserAccount
from wallets.constants import SNAPSHOT_REASON_DAILY
from wallets.exceptions import InvalidTransactionException
from wallets.models import (
    Holding,
    HoldingSnapshot,
    Wallet,
    WalletBalanceProjection,
    WalletSubmissionFamily,
)
from wallets.services.signed_transfers import expected_chain_id


def membership_identity(wallet, principal_id):
    if principal_id is None:
        return None
    membership = (
        UserAccount.user_profiles.through.objects.select_for_update(of=("self",))
        .filter(useraccount_id=wallet.user_account_id, userprofile__user_id=principal_id)
        .values_list("pk", "userprofile_id")
        .first()
    )
    if membership is None:
        raise InvalidTransactionException("This wallet is no longer available to the requesting user.")
    return membership


def asset_specs(wallet, asset_ids):
    native = native_asset_for_chain(wallet.chain)
    specs = []
    for asset in Asset.objects.select_for_update().filter(pk__in=set(asset_ids) | {native.pk}).order_by("pk"):
        deployment = (
            AssetChainDeployment.objects.select_for_update().filter(asset=asset, chain__iexact=wallet.chain).first()
        )
        if deployment is None or not deployment.is_active or not asset.is_active:
            raise InvalidTransactionException("Wallet asset configuration is unavailable.")
        if asset.pk == native.pk:
            valid = (
                asset.asset_type == AssetType.NATIVE_CRYPTO.value
                and deployment.contract_address is None
                and deployment.decimals == 18
            )
        else:
            valid = (
                asset.is_verified
                and asset.asset_type != AssetType.TOKENIZED_SECURITY.value
                and bool(deployment.contract_address)
                and 0 <= deployment.decimals <= 255
            )
        if not valid:
            raise InvalidTransactionException("Wallet asset configuration is unavailable.")
        specs.append(
            (
                str(asset.pk),
                asset.asset_type,
                asset.is_active,
                asset.is_verified,
                str(deployment.pk),
                deployment.contract_address.lower() if deployment.contract_address else None,
                deployment.decimals,
                tuple(getattr(asset, field.attname) for field in asset._meta.concrete_fields),
                tuple(getattr(deployment, field.attname) for field in deployment._meta.concrete_fields),
            )
        )
    if len(specs) != len(set(asset_ids) | {native.pk}):
        raise InvalidTransactionException("Wallet asset configuration is unavailable.")
    return tuple(specs)


def capture_balance_target(wallet, *, extra_asset_ids=(), principal_id=None):
    families = list(WalletSubmissionFamily.objects.select_for_update().filter(wallet=wallet).order_by("pk"))
    specs = asset_specs(wallet, {family.asset_id for family in families} | set(extra_asset_ids))
    by_asset = {spec[0]: spec for spec in specs}
    for family in families:
        spec = by_asset[str(family.asset_id)]
        if family.deployment_id is not None and (
            str(family.deployment_id),
            family.original_intent["token_contract"].lower(),
            family.original_intent["asset_decimals"],
        ) != (spec[4], spec[5], spec[6]):
            raise InvalidTransactionException("The recorded token deployment changed.")
    return {
        "wallet": (wallet.pk, wallet.user_account_id, wallet.address, wallet.chain, wallet.verification_status),
        "membership": membership_identity(wallet, principal_id),
        "families": tuple((family.pk, family.generation) for family in families),
        "assets": specs,
        "holdings": tuple(
            Holding.objects.select_for_update()
            .filter(wallet=wallet, asset_id__in=[spec[0] for spec in specs])
            .order_by("pk")
            .values_list("pk", "balance_version")
        ),
    }


def read_balance_state(wallet, specs, *, client=None):
    try:
        client = client or get_blockchain_client(wallet.chain)
        chain_id = expected_chain_id(wallet.chain)
        actual_chain_id = client.assert_expected_chain()
        if type(actual_chain_id) is not int or actual_chain_id != chain_id:
            raise ValueError("Unexpected chain")
        contracts = sorted(spec[5] for spec in specs if spec[5])
        observed = (
            client.get_mined_nonce(wallet.address, token_contracts=contracts)
            if contracts
            else client.get_mined_nonce(wallet.address)
        )
        if (
            not isinstance(observed, Mapping)
            or type(observed.get("chain_id")) is not int
            or observed.get("chain_id") != chain_id
        ):
            raise ValueError("Invalid sender observation")
        nonce = nonnegative_integer(observed.get("nonce"), maximum=2**64 - 1)
        balance = nonnegative_integer(observed.get("balance_wei"), maximum=2**256 - 1, encoded=True)
        height = nonnegative_integer(observed.get("block_number"), maximum=2**63 - 1)
        block_hash = normalized_hash(observed.get("block_hash"))
        token_balances = observed.get("token_balances", {})
        if (
            nonce is None
            or balance is None
            or height is None
            or block_hash is None
            or not isinstance(token_balances, Mapping)
        ):
            raise ValueError("Invalid sender observation")
        tokens = {}
        for contract in contracts:
            value = nonnegative_integer(token_balances.get(contract), maximum=2**256 - 1, encoded=True)
            if value is None:
                raise ValueError("Invalid token balance observation")
            tokens[contract] = str(value)
    except Exception:
        raise InvalidTransactionException("The mined sender state could not be verified. Retry the request.") from None
    return {
        "chain_id": chain_id,
        "nonce": nonce,
        "balance_wei": str(balance),
        "block_number": height,
        "block_hash": "0x" + block_hash,
        **({"token_balances": tokens} if contracts else {}),
    }


def exposure_totals(families, nonce, *, exclude=None):
    native = Decimal("0")
    tokens = {}
    with localcontext() as context:
        context.prec = 90
        for family in families:
            if family.pk == exclude or family.nonce < nonce:
                continue
            native += family.native_exposure
            tokens[family.asset_id] = tokens.get(family.asset_id, Decimal("0")) + family.token_exposure
    return native, tokens


def install_projection(wallet, target, observation):
    families = list(WalletSubmissionFamily.objects.select_for_update().filter(wallet=wallet).order_by("pk"))
    native, tokens = exposure_totals(families, observation["nonce"])
    quantities = {}
    with localcontext() as context:
        context.prec = 90
        for spec in target["assets"]:
            if spec[5] is None:
                raw = Decimal(observation["balance_wei"]).scaleb(-18)
                reserved = native
            else:
                raw = Decimal(observation["token_balances"][spec[5]]).scaleb(-spec[6])
                reserved = sum(
                    (quantity for asset_id, quantity in tokens.items() if str(asset_id) == spec[0]), Decimal("0")
                )
            quantity = max(Decimal("0"), raw - reserved)
            if quantity >= Decimal(10) ** 22 or quantity != quantity.quantize(Decimal("1e-18")):
                raise InvalidTransactionException("The observed balance cannot be represented by this wallet.")
            quantities[spec[0]] = str(quantity)
    projection = WalletBalanceProjection.objects.create(
        wallet=wallet,
        user_account_id=wallet.user_account_id,
        observation=observation,
        reservations=[
            {
                "family_id": str(family.pk),
                "generation": family.generation,
                "native": str(family.native_exposure),
                "token": str(family.token_exposure),
                "consumed": family.nonce < observation["nonce"],
            }
            for family in families
        ],
        quantities=quantities,
    )
    holdings = {}
    for asset_id, quantity in quantities.items():
        holding, _ = Holding.objects.select_for_update().get_or_create(
            wallet=wallet, asset_id=asset_id, defaults={"quantity": Decimal("0")}
        )
        holding.quantity = Decimal(quantity)
        holding.last_synced_at = timezone.now()
        holding.sync_version = uuid4()
        holding.balance_version = holding.sync_version
        holding.balance_projection = projection
        holding.save(
            update_fields=[
                "quantity",
                "last_synced_at",
                "sync_version",
                "balance_version",
                "balance_projection",
                "updated_at",
            ]
        )
        HoldingSnapshot.objects.update_or_create(
            holding=holding,
            snapshot_date=timezone.now().date(),
            defaults={"quantity": holding.quantity},
            create_defaults={"quantity": holding.quantity, "snapshot_reason": SNAPSHOT_REASON_DAILY},
        )
        holdings[asset_id] = holding
    return holdings


def sync_family_balances(wallet, *, extra_asset_ids=(), client=None):
    with atomic():
        locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
        target = capture_balance_target(locked, extra_asset_ids=extra_asset_ids)
    observation = read_balance_state(locked, target["assets"], client=client)
    with atomic():
        locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
        if capture_balance_target(locked, extra_asset_ids=extra_asset_ids) != target:
            return None
        return install_projection(locked, target, observation)
