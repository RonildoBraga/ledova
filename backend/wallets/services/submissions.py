import logging
from collections.abc import Mapping
from decimal import Decimal, localcontext

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from web3 import Web3

from assets.models import Asset, AssetChainDeployment
from integrations.blockchain import get_blockchain_client
from integrations.blockchain.receipts import transaction_hash_matches
from shared.constants import normalize_chain
from shared.db import atomic
from tokens.services.signed_transactions import decode_signed_transaction
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, Transaction, Wallet, WalletSubmission
from wallets.services import transaction_confirmation
from wallets.services.chain import token_deployment_decimals
from wallets.services.signed_transfers import (
    _recordable,
    expected_chain_id,
    plan_signed_transfer,
)

logger = logging.getLogger(__name__)
MAX_RECORDED_NONCE = 2**63 - 1


def submit_evm_transfer(wallet, signed_transaction, *, principal_id, token_contract=None):
    if principal_id is None:
        raise InvalidTransactionException("A wallet submission requires its requesting user.")
    raw, decoded = _decode(signed_transaction)
    tx_hash = Web3.keccak(raw).to_0x_hex()
    with atomic(durable=True):
        locked_wallet = (
            Wallet.objects.select_for_update(of=("self",))
            .filter(user_account__user_profiles__user_id=principal_id)
            .get(pk=wallet.pk)
        )
        chain = normalize_chain(locked_wallet.chain)
        if decoded.sender.lower() != locked_wallet.address.lower() or decoded.chain_id != expected_chain_id(chain):
            raise InvalidTransactionException("The signed submission does not match this wallet and chain.")
        submission = WalletSubmission.objects.filter(wallet=locked_wallet, tx_hash=tx_hash).first()
        if submission is not None:
            if bytes(submission.raw_transaction) != raw:
                raise InvalidTransactionException("The recorded submission does not match these signed bytes.")
        else:
            submission = _record_submission(locked_wallet, raw, decoded, tx_hash, token_contract)
    attempt_submission(submission.pk)
    tx = Transaction.objects.get(pk=submission.transaction_id)
    quantity = (
        Holding.objects.filter(wallet_id=tx.wallet_id, asset_id=tx.asset_id).values_list("quantity", flat=True).first()
    )
    return {
        "success": True,
        "txHash": submission.tx_hash,
        "status": tx.status,
        "message": "Transaction accepted for broadcast.",
        "pendingTransaction": {
            "transaction_id": str(tx.pk),
            "tx_hash": tx.tx_hash,
            "status": tx.status,
            "holding_quantity": str(quantity if quantity is not None else Decimal("0")),
        },
    }


def _decode(signed_transaction):
    try:
        raw = bytes.fromhex(signed_transaction.removeprefix("0x"))
        decoded = decode_signed_transaction(raw)
    except (ValueError, TypeError, AttributeError):
        raise InvalidTransactionException("The signed transaction could not be decoded.") from None
    if not 0 <= decoded.nonce <= MAX_RECORDED_NONCE:
        raise InvalidTransactionException("The signed nonce is outside the supported storage range.")
    return raw, decoded


def _signed_fee(decoded):
    price = decoded.max_fee_per_gas if decoded.envelope_type == 2 else decoded.gas_price
    if decoded.gas_limit <= 0 or price is None or price < 0:
        raise InvalidTransactionException("The signed gas limit and fee cap are invalid.")
    if decoded.envelope_type == 2 and (
        decoded.max_priority_fee_per_gas is None or not 0 <= decoded.max_priority_fee_per_gas <= price
    ):
        raise InvalidTransactionException("The signed priority fee exceeds its maximum fee.")
    fee_units = decoded.gas_limit * price
    with localcontext() as context:
        context.prec = len(str(fee_units)) + 20
        return _recordable(Decimal(fee_units).scaleb(-18))


def _record_submission(wallet, raw, decoded, tx_hash, declared_contract):
    if Transaction.objects.filter(wallet=wallet, tx_hash=tx_hash).exists():
        raise InvalidTransactionException("This transaction already has history without a signed submission record.")
    if WalletSubmission.objects.filter(wallet=wallet, chain_id=decoded.chain_id, nonce=decoded.nonce).exists():
        raise InvalidTransactionException("Different signed bytes have already been recorded for this wallet nonce.")
    deployment = None
    if decoded.data and decoded.to:
        deployment = (
            AssetChainDeployment.objects.select_for_update()
            .filter(chain__iexact=wallet.chain, contract_address__iexact=decoded.to)
            .first()
        )
        if deployment is not None:
            Asset.objects.select_for_update().get(pk=deployment.asset_id)
    plan = plan_signed_transfer(wallet, raw.hex(), declared_contract)
    if plan is None:
        raise InvalidTransactionException("A signed EVM transfer is required.")
    fee = _signed_fee(decoded)
    recorded = transaction_confirmation.create_pending_transaction(
        wallet, tx_hash, plan.to_address, plan.amount, transaction_fee=fee, token_contract=plan.token_contract
    )
    tx = Transaction.objects.get(pk=recorded["transaction_id"])
    tx.nonce = decoded.nonce
    tx.save(update_fields=["nonce", "updated_at"])
    decimals = token_deployment_decimals(tx.asset, wallet.chain, plan.token_contract) if plan.token_contract else 18
    return _store_submission(
        wallet=wallet,
        user_account_id=wallet.user_account_id,
        transaction=tx,
        asset_id=tx.asset_id,
        deployment=deployment if plan.token_contract else None,
        chain=normalize_chain(wallet.chain),
        chain_id=decoded.chain_id,
        sender_address=decoded.sender.lower(),
        nonce=decoded.nonce,
        tx_hash=tx_hash,
        raw_transaction=raw,
        intent={
            "to_address": plan.to_address,
            "amount": str(plan.amount),
            "token_contract": plan.token_contract,
            "asset_decimals": decimals,
            "raw_amount": str(int.from_bytes(decoded.data[-32:], "big") if plan.token_contract else decoded.value),
            "maximum_fee": str(fee),
            "envelope_type": decoded.envelope_type,
            "envelope_to": decoded.to,
            "value": str(decoded.value),
            "gas_limit": str(decoded.gas_limit),
            "gas_price": str(decoded.gas_price) if decoded.gas_price is not None else None,
            "max_fee_per_gas": str(decoded.max_fee_per_gas) if decoded.max_fee_per_gas is not None else None,
            "max_priority_fee_per_gas": (
                str(decoded.max_priority_fee_per_gas) if decoded.max_priority_fee_per_gas is not None else None
            ),
        },
    )


def _store_submission(**fields):
    try:
        return WalletSubmission.objects.create(**fields)
    except IntegrityError:
        raise InvalidTransactionException("This signed transaction or sender nonce is already recorded.") from None


def attempt_submission(submission_id):
    submission = WalletSubmission.objects.select_related("transaction", "wallet").filter(pk=submission_id).first()
    if submission is None:
        return "not_found"
    if submission.transaction.status != "pending":
        return "already_processed"
    now = timezone.now()
    WalletSubmission.objects.filter(pk=submission.pk).filter(
        Q(last_attempt_at__isnull=True) | Q(last_attempt_at__lte=now)
    ).update(last_attempt_at=now, updated_at=now)
    try:
        raw, decoded = _decode(bytes(submission.raw_transaction).hex())
    except InvalidTransactionException:
        return "identity_unavailable"
    if (
        Web3.keccak(raw).to_0x_hex() != submission.tx_hash
        or decoded.chain_id != submission.chain_id
        or decoded.nonce != submission.nonce
        or decoded.sender.lower() != submission.sender_address
        or submission.wallet.user_account_id != submission.user_account_id
        or submission.wallet.address.lower() != submission.sender_address
        or normalize_chain(submission.wallet.chain) != submission.chain
    ):
        return "identity_unavailable"
    try:
        client = get_blockchain_client(submission.chain)
        if client.assert_expected_chain() != submission.chain_id:
            return "chain_unavailable"
        receipt = client.get_transaction_receipt(submission.tx_hash)
        if receipt is not None:
            if isinstance(receipt, Mapping) and transaction_hash_matches(
                receipt.get("transactionHash"), submission.tx_hash
            ):
                return "receipt_available"
            return "receipt_identity_unavailable"
        acknowledged_hash = client.broadcast_transaction("0x" + raw.hex())
        if not transaction_hash_matches(acknowledged_hash, submission.tx_hash):
            return "acknowledgement_unavailable"
    except Exception:
        logger.warning("Wallet submission delivery remains unresolved")
        return "delivery_unavailable"
    WalletSubmission.objects.filter(pk=submission.pk, acknowledged_at__isnull=True).update(
        acknowledged_at=timezone.now(), updated_at=timezone.now()
    )
    return "acknowledged"
