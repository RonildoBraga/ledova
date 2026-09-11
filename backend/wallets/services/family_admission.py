from decimal import Decimal, localcontext

from django.db import IntegrityError

from tokens.services.signed_transactions import decode_signed_transaction
from wallets.exceptions import InvalidTransactionException
from wallets.models import WalletSubmissionFamily
from wallets.services.family_balances import exposure_totals


def family_for_nonce(wallet, decoded):
    return (
        WalletSubmissionFamily.objects.select_for_update()
        .filter(wallet=wallet, chain_id=decoded.chain_id, nonce=decoded.nonce)
        .first()
    )


def attempt_kind(family, decoded):
    if family is None:
        return "original"
    if family.winner_id is not None or family.selected_id is None:
        raise InvalidTransactionException("This sender nonce is not available for another attempt.")
    original = family.attempts.get(tx_hash=family.original_tx_hash)
    original_decoded = decode_signed_transaction(bytes(original.raw_transaction))
    selected = decode_signed_transaction(bytes(family.selected.raw_transaction))
    same_transfer = (decoded.to, decoded.value, decoded.data) == (
        original_decoded.to,
        original_decoded.value,
        original_decoded.data,
    )
    cancellation = (
        decoded.to is not None
        and decoded.to.lower() == decoded.sender.lower()
        and decoded.value == 0
        and decoded.data == b""
    )
    if not same_transfer and not cancellation:
        raise InvalidTransactionException(
            "A replacement must preserve the original transfer or cancel it to this sender."
        )
    price = decoded.max_fee_per_gas if decoded.envelope_type == 2 else decoded.gas_price
    old_price = selected.max_fee_per_gas if selected.envelope_type == 2 else selected.gas_price
    tip = decoded.max_priority_fee_per_gas if decoded.envelope_type == 2 else decoded.gas_price
    old_tip = selected.max_priority_fee_per_gas if selected.envelope_type == 2 else selected.gas_price
    if price <= old_price or tip < old_tip:
        raise InvalidTransactionException(
            "A replacement must increase its maximum fee rate without reducing its priority rate."
        )
    return "cancellation" if cancellation and not same_transfer else "speed_up"


def admit_exposure(wallet, family, kind, decoded, fee, asset, plan, observation):
    with localcontext() as context:
        context.prec = 90
        own_native = Decimal(decoded.value).scaleb(-18) + fee
        native = max(family.native_exposure, own_native) if family is not None else own_native
        token = family.token_exposure if family is not None else (plan.amount if plan.token_contract else Decimal("0"))
        others = list(WalletSubmissionFamily.objects.select_for_update().filter(wallet=wallet))
        other_native, other_tokens = exposure_totals(
            others, observation["nonce"], exclude=family.pk if family else None
        )
        balance = Decimal(observation["balance_wei"]).scaleb(-18)
        bounded_cancel = family is not None and kind == "cancellation" and native == family.native_exposure
        required = own_native if bounded_cancel else native
        if other_native + required > balance:
            raise InvalidTransactionException(
                "The observed native balance cannot cover outstanding wallet commitments."
            )
        required_tokens = dict(other_tokens)
        token_specs = {
            row.asset_id: (row.original_intent["token_contract"], row.original_intent["asset_decimals"])
            for row in others
            if row.deployment_id is not None
        }
        original_asset_id = family.asset_id if family else asset.pk
        contract = family.original_intent["token_contract"] if family else plan.token_contract
        if contract:
            decimals = (
                family.original_intent["asset_decimals"]
                if family
                else asset.get_deployment_for_chain(wallet.chain).decimals
            )
            token_specs[original_asset_id] = (contract, decimals)
            if not bounded_cancel:
                required_tokens[original_asset_id] = required_tokens.get(original_asset_id, Decimal("0")) + token
        for asset_id, quantity in required_tokens.items():
            if not quantity:
                continue
            contract, decimals = token_specs[asset_id]
            token_balance = Decimal(observation["token_balances"][contract.lower()]).scaleb(-decimals)
            if quantity > token_balance:
                raise InvalidTransactionException(
                    "The observed token balance cannot cover outstanding wallet commitments."
                )
        return native, token


def create_family(**fields):
    try:
        return WalletSubmissionFamily.objects.create(**fields)
    except IntegrityError:
        raise InvalidTransactionException("This signed transaction or sender nonce is already recorded.") from None
