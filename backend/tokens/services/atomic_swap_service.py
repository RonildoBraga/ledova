import logging
import secrets
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal, localcontext
from typing import Optional

from django.conf import settings
from django.utils import timezone
from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_typed_data
from web3 import Web3

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain import get_base_chain_client
from operators.settlement import require_deployment
from shared.db import atomic, use_operator
from shared.utils.blockchain import decode_exception_to_message
from shared.utils.token_amounts import token_base_units
from tokens.constants import MAX_SETTLEMENT_UNITS
from tokens.events import publish_trading_event
from tokens.exceptions import (
    AtomicSwapNotConfiguredException,
    InsufficientBalanceException,
    InvalidSettlementAmountException,
    SettlementApprovalUncertain,
    SettlementContextChanged,
    SwapExecutionException,
    SwapExpiredException,
    SwapNotReadyException,
    SwapSignatureException,
)
from tokens.models import (
    SwapOrder,
    SwapOrderStatus,
    TransferOrder,
    TransferOrderStatus,
    TransferOrderType,
)
from tokens.services.settlement_context import (
    assert_current_settlement,
    capture_settlement_context,
    recorded_settlement_context,
    settlement_execution_arguments,
)
from tokens.services.signed_transactions import decode_signed_transaction
from tokens.services.trading_locks import (
    hash_identity,
    lock_current_claim,
    lock_orders,
    swap_terms,
)

logger = logging.getLogger(__name__)

MAX_UINT256 = 2**256 - 1


def payment_address(swap_order) -> str:
    return recorded_settlement_context(swap_order)["typed_data"]["message"]["paymentToken"]


def configured_relayer_key() -> str:
    key = getattr(settings, "BLOCKCHAIN_OPERATOR_KEY", None)
    if not key:
        raise AtomicSwapNotConfiguredException("Relayer private key not configured")
    return key


def get_typed_data(swap_order: SwapOrder) -> dict:
    return recorded_settlement_context(swap_order)["typed_data"]


def _generate_nonce() -> int:
    return secrets.randbits(63)


def settlement_contract(swap_order):
    return recorded_settlement_context(swap_order)["typed_data"]["domain"]["verifyingContract"]


def assert_provider_settlement(swap_order):
    context = assert_current_settlement(swap_order)
    try:
        actual_chain = get_base_chain_client().assert_expected_chain()
    except Exception as exc:
        raise SettlementContextChanged() from exc
    if actual_chain != int(context["typed_data"]["domain"]["chainId"]):
        raise SettlementContextChanged()
    assert_current_settlement(swap_order)


def check_allowance(token_address: str, owner_address: str, spender) -> int:
    token_contract = get_base_chain_client().load_contract("ShareToken", token_address)
    allowance = get_base_chain_client().call_contract_function(
        token_contract.functions.allowance(
            get_base_chain_client().to_checksum_address(owner_address),
            get_base_chain_client().to_checksum_address(spender),
        )
    )
    return allowance


def check_balance(token_address: str, owner_address: str) -> int:
    token_contract = get_base_chain_client().load_contract("ShareToken", token_address)
    balance = get_base_chain_client().call_contract_function(
        token_contract.functions.balanceOf(
            get_base_chain_client().to_checksum_address(owner_address),
        )
    )
    return balance


def validate_swap_balances(swap_order: SwapOrder) -> None:
    assert_provider_settlement(swap_order)
    context = recorded_settlement_context(swap_order)
    seller_balance = check_balance(
        context["share_token"]["address"],
        swap_order.seller_address,
    )
    if seller_balance < swap_order.share_amount:
        raise InsufficientBalanceException(
            balance=seller_balance,
            required=swap_order.share_amount,
            token_symbol=context["share_token"]["symbol"],
        )

    buyer_balance = check_balance(
        payment_address(swap_order),
        swap_order.buyer_address,
    )
    if buyer_balance < swap_order.payment_amount:
        raise InsufficientBalanceException(
            balance=buyer_balance,
            required=swap_order.payment_amount,
            token_symbol=context["payment_asset"]["symbol"],
            decimals=context["payment_asset"]["deployment_decimals"],
        )
    assert_provider_settlement(swap_order)


def check_swap_allowances(swap_order: SwapOrder) -> dict:
    assert_provider_settlement(swap_order)
    context = recorded_settlement_context(swap_order)
    share_address = context["share_token"]["address"]
    spender = settlement_contract(swap_order)
    seller_allowance = check_allowance(
        share_address,
        swap_order.seller_address,
        spender,
    )
    seller_has_allowance = seller_allowance >= swap_order.share_amount

    buyer_allowance = check_allowance(
        payment_address(swap_order),
        swap_order.buyer_address,
        spender,
    )
    buyer_has_allowance = buyer_allowance >= swap_order.payment_amount

    assert_provider_settlement(swap_order)
    return {
        "seller": {
            "address": swap_order.seller_address,
            "token": share_address,
            "token_symbol": context["share_token"]["symbol"],
            "required_amount": swap_order.share_amount,
            "current_allowance": seller_allowance,
            "has_sufficient_allowance": seller_has_allowance,
        },
        "buyer": {
            "address": swap_order.buyer_address,
            "token": payment_address(swap_order),
            "token_symbol": context["payment_asset"]["symbol"],
            "required_amount": swap_order.payment_amount,
            "current_allowance": buyer_allowance,
            "has_sufficient_allowance": buyer_has_allowance,
        },
    }


def get_approval_transaction_data(
    swap_order: SwapOrder,
    user_role: str,
    unlimited: bool = True,
) -> dict:
    assert_provider_settlement(swap_order)
    context = recorded_settlement_context(swap_order)
    if user_role == "seller":
        token_address = context["share_token"]["address"]
        owner_address = swap_order.seller_address
        amount = MAX_UINT256 if unlimited else swap_order.share_amount
        token_symbol = context["share_token"]["symbol"]
    elif user_role == "buyer":
        token_address = payment_address(swap_order)
        owner_address = swap_order.buyer_address
        amount = MAX_UINT256 if unlimited else swap_order.payment_amount
        token_symbol = context["payment_asset"]["symbol"]
    else:
        raise ValueError(f"Invalid user_role: {user_role}")

    token_contract = get_base_chain_client().load_contract("ShareToken", token_address)
    approve_fn = token_contract.functions.approve(
        get_base_chain_client().to_checksum_address(settlement_contract(swap_order)),
        amount,
    )
    tx = get_base_chain_client().build_transaction(
        approve_fn,
        from_address=owner_address,
    )
    assert_provider_settlement(swap_order)
    return {
        "transaction": {
            "to": token_address,
            "from": owner_address,
            "data": tx.get("data", ""),
            "value": "0x0",
            "gas": hex(tx.get("gas", 100000)),
            "gasPrice": hex(tx.get("gasPrice", 0)),
            "nonce": hex(tx.get("nonce", 0)),
            "chainId": hex(get_base_chain_client().chain_id),
        },
        "description": f"Approve AtomicSwap contract to transfer {token_symbol}",
        "token_address": token_address,
        "token_symbol": token_symbol,
        "spender": settlement_contract(swap_order),
        "amount": str(amount),
        "unlimited": unlimited,
    }


def broadcast_settlement_approval(swap_order, user_role, signed_transaction, admission):
    from tokens.services import token_transfer_service
    from tokens.services.trading_order_access import require_pending_settlement

    context = require_pending_settlement(swap_order)
    try:
        raw_transaction = bytes.fromhex(signed_transaction.removeprefix("0x"))
        decoded = decode_signed_transaction(raw_transaction)
    except ValueError as exc:
        raise SettlementContextChanged() from exc
    token = (
        context["share_token"]["address"] if user_role == "seller" else context["payment_asset"]["deployment_address"]
    )
    spender = context["typed_data"]["domain"]["verifyingContract"]
    expected_data = (
        bytes.fromhex("095ea7b3") + bytes.fromhex(spender[2:]).rjust(32, b"\x00") + MAX_UINT256.to_bytes(32, "big")
    )
    if (
        decoded.sender != context[user_role]["address"]
        or decoded.chain_id != int(context["typed_data"]["domain"]["chainId"])
        or decoded.to != token
        or decoded.value != 0
        or decoded.data != expected_data
    ):
        raise SettlementContextChanged()
    assert_provider_settlement(swap_order)
    current = admission(swap_order)
    require_pending_settlement(current)
    expected_hash = Web3.to_hex(Web3.keccak(raw_transaction))
    try:
        returned_hash, receipt = token_transfer_service.broadcast_transfer(signed_transaction)
        if (
            hash_identity(returned_hash) != hash_identity(expected_hash)
            or hash_identity(receipt.get("transactionHash")) != hash_identity(expected_hash)
            or type(receipt.get("status")) is not int
            or receipt["status"] != 1
        ):
            raise SettlementApprovalUncertain(expected_hash)
    except Exception as exc:
        raise SettlementApprovalUncertain(expected_hash) from exc
    return expected_hash, receipt


@atomic()
def create_swap_order(
    sell_order: TransferOrder,
    buy_order: TransferOrder,
    expires_hours: Optional[float] = None,
    share_amount: Optional[int] = None,
    price_per_share=None,
) -> SwapOrder:
    locked = {
        order.pk: order for order in lock_orders(TransferOrder.objects.filter(pk__in=[sell_order.pk, buy_order.pk]))
    }
    sell_order = locked[sell_order.pk]
    buy_order = locked[buy_order.pk]
    if sell_order.order_type != TransferOrderType.SELL:
        raise ValueError("sell_order must be a SELL order")
    if buy_order.order_type != TransferOrderType.BUY:
        raise ValueError("buy_order must be a BUY order")

    token = sell_order.token
    payment_asset = buy_order.payment_asset or sell_order.payment_asset

    if not payment_asset:
        raise ValueError("Payment asset must be specified on at least one order")

    if share_amount is None:
        share_amount = sell_order.quantity

    if price_per_share is None:
        price_per_share = sell_order.price_per_share

    if (
        type(share_amount) is not int
        or not 0 < share_amount <= MAX_SETTLEMENT_UNITS
        or not isinstance(price_per_share, Decimal)
        or not price_per_share.is_finite()
        or price_per_share <= 0
    ):
        raise InvalidSettlementAmountException()
    deployment = require_deployment(payment_asset)
    with localcontext() as context:
        context.prec = max(78, len(price_per_share.as_tuple().digits) + len(str(share_amount)))
        try:
            payment_amount = token_base_units(share_amount * price_per_share, deployment.decimals)
        except ValueError as exc:
            raise InvalidSettlementAmountException() from exc
    if payment_amount > MAX_SETTLEMENT_UNITS:
        raise InvalidSettlementAmountException()
    nonce = _generate_nonce()

    if expires_hours is None:
        expires_hours = getattr(settings, "SWAP_ORDER_EXPIRY_HOURS", 0.25)
    expires_at = timezone.now() + timedelta(hours=expires_hours)

    swap_order = SwapOrder(
        sell_order=sell_order,
        buy_order=buy_order,
        share_token=token,
        payment_asset=payment_asset,
        seller_address=Web3.to_checksum_address(sell_order.wallet_address),
        buyer_address=Web3.to_checksum_address(buy_order.wallet_address),
        share_amount=share_amount,
        payment_amount=payment_amount,
        nonce=nonce,
        order_hash="",
        expires_at=expires_at,
        expiry_release_eligible=True,
        status=SwapOrderStatus.CREATED,
    )
    capture_settlement_context(swap_order, deployment, price_per_share)
    swap_order.save()

    sell_order.status = TransferOrderStatus.PENDING_SIGNATURE
    sell_order.save(update_fields=["status", "updated_at"])
    buy_order.status = TransferOrderStatus.PENDING_SIGNATURE
    buy_order.save(update_fields=["status", "updated_at"])

    logger.info(f"Created swap order {swap_order.uuid}: {share_amount} shares for {payment_amount} payment")

    return swap_order


def verify_signature(swap_order: SwapOrder, signature: str, expected_signer: str) -> bool:
    try:
        typed_data = get_typed_data(swap_order)
        structured_message = encode_typed_data(full_message=typed_data)
        recovered = Account.recover_message(structured_message, signature=signature)
        expected_checksum = Web3.to_checksum_address(expected_signer)

        return recovered.lower() == expected_checksum.lower()
    except Exception as e:
        logger.warning(f"Signature verification failed: {e}", exc_info=True)
        return False


def submit_signature(
    swap_order: SwapOrder,
    signature: str,
    signer_address: str,
    admission=None,
) -> SwapOrder:
    snapshot = SwapOrder.objects.get(pk=swap_order.pk)
    recorded_settlement_context(snapshot)
    if admission:
        admission(snapshot)
    signer_checksum = Web3.to_checksum_address(signer_address)
    if signer_checksum == Web3.to_checksum_address(snapshot.seller_address):
        is_seller = True
        expected_signer = snapshot.seller_address
    elif signer_checksum == Web3.to_checksum_address(snapshot.buyer_address):
        is_seller = False
        expected_signer = snapshot.buyer_address
    else:
        raise SwapSignatureException("Signer is neither the buyer nor seller")
    if not verify_signature(snapshot, signature, expected_signer):
        raise SwapSignatureException("Invalid signature")
    return _store_signature(snapshot, signature, is_seller, admission=admission)


@atomic()
def _store_signature(snapshot, signature, is_seller, admission=None):
    swap = SwapOrder.objects.select_for_update(of=("self",)).get(pk=snapshot.pk)
    recorded_settlement_context(swap)
    if swap_terms(swap) != swap_terms(snapshot):
        raise SwapSignatureException("The swap changed while its signature was being checked")
    if admission:
        admission(swap)
    stored = swap.seller_signature if is_seller else swap.buyer_signature
    if stored:
        if stored != signature:
            raise SwapSignatureException("This party has already signed the swap")
        return swap
    assert_current_settlement(swap)
    allowed = (
        (SwapOrderStatus.CREATED, SwapOrderStatus.BUYER_SIGNED)
        if is_seller
        else (SwapOrderStatus.CREATED, SwapOrderStatus.SELLER_SIGNED)
    )
    if swap.status not in allowed or swap.transaction_id is not None or swap.tx_hash:
        raise SwapNotReadyException()
    if swap.deadline_passed:
        raise SwapExpiredException()
    if is_seller:
        swap.add_seller_signature(signature)
    else:
        swap.add_buyer_signature(signature)
    publish_trading_event("swap_signed", str(swap.share_token_id))
    return swap


def execute_swap(swap_order: SwapOrder, admission=None) -> str:
    if admission:
        admission(swap_order)
    assert_provider_settlement(swap_order)
    swap, tx_record = _claim_execution(swap_order.pk, admission=admission)
    try:
        validate_swap_balances(swap)
        signed_tx = _prepare_attempt(swap)
    except SettlementContextChanged:
        raise
    except Exception as exc:
        told_to_the_parties = decode_exception_to_message(exc, "Swap execution failed")
        _record_never_sent(swap, tx_record, str(exc), told_to_the_parties)
        if isinstance(exc, InsufficientBalanceException):
            raise
        raise SwapExecutionException(f"Swap execution failed: {told_to_the_parties}") from exc
    assert_provider_settlement(swap)
    if admission:
        admission(swap)
    _admit_claim(swap, tx_record)
    try:
        tx_hash = get_base_chain_client().send_raw_transaction(signed_tx)
    except Exception as exc:
        _record_unknown_fate(swap, tx_record, str(exc))
        raise SwapExecutionException(
            f"Swap execution outcome is unknown: {decode_exception_to_message(exc, 'no response from the chain')}"
        ) from exc
    return _record_broadcast(swap, tx_record, tx_hash)


@atomic()
def _admit_claim(swap, transaction):
    current = lock_current_claim(swap, transaction)
    if current is None:
        raise SwapNotReadyException()
    assert_current_settlement(current[0])
    if current[0].deadline_passed:
        raise SwapExpiredException()


@atomic(durable=True)
def _claim_execution(swap_id, admission=None):
    swap = SwapOrder.objects.select_for_update(of=("self",)).get(pk=swap_id)
    recorded_settlement_context(swap)
    if not swap.is_ready or swap.transaction_id is not None or swap.tx_hash:
        raise SwapNotReadyException()
    if swap.deadline_passed:
        raise SwapExpiredException()
    if admission:
        admission(swap)
    assert_current_settlement(swap)
    relayer_account = Account.from_key(configured_relayer_key())
    arguments = settlement_execution_arguments(swap)
    tx_record = _new_transaction_record(swap, relayer_account.address, arguments)
    swap.mark_executing(transaction=tx_record)
    return swap, tx_record


def _prepare_attempt(swap_order: SwapOrder):
    assert_provider_settlement(swap_order)
    relayer_account = Account.from_key(configured_relayer_key())
    execute_fn = _execute_swap_call(swap_order)
    tx = get_base_chain_client().build_transaction(execute_fn, from_address=relayer_account.address)
    return get_base_chain_client().sign_transaction(tx, configured_relayer_key())


def _execute_swap_call(swap_order: SwapOrder):
    address = settlement_contract(swap_order)
    message = get_typed_data(swap_order)["message"]
    contract = get_base_chain_client().load_contract("AtomicSwap", address)

    return contract.functions.executeSwap(
        Web3.to_checksum_address(message["seller"]),
        Web3.to_checksum_address(message["buyer"]),
        Web3.to_checksum_address(message["shareToken"]),
        Web3.to_checksum_address(message["paymentToken"]),
        int(message["shareAmount"]),
        int(message["paymentAmount"]),
        int(message["nonce"]),
        int(message["deadline"]),
        _signature_bytes(swap_order.seller_signature),
        _signature_bytes(swap_order.buyer_signature),
    )


def _new_transaction_record(swap_order: SwapOrder, relayer_address: str, arguments: dict):
    return BlockchainTransaction.objects.create(
        tx_type=TransactionType.ATOMIC_SWAP,
        status=TransactionStatus.PENDING,
        from_address=relayer_address,
        to_address=settlement_contract(swap_order),
        function_name="executeSwap",
        function_args=arguments,
        related_model="tokens.SwapOrder",
        related_uuid=swap_order.uuid,
    )


@atomic(durable=True)
def _record_never_sent(swap_order, tx_record, raw_error, told_to_the_parties):
    current = lock_current_claim(swap_order, tx_record, with_orders=True)
    if current is None:
        return
    swap, transaction = current
    if transaction.tx_hash or transaction.status not in (TransactionStatus.PENDING, TransactionStatus.FAILED):
        return
    transaction.mark_failed(raw_error)
    swap.mark_failed(told_to_the_parties)
    logger.error("Swap %s was never sent", swap.uuid)
    publish_trading_event("swap_failed", str(swap.share_token_id))


@atomic()
def _record_unknown_fate(swap_order, tx_record, raw_error):
    current = lock_current_claim(swap_order, tx_record)
    if current is None:
        return
    _swap, transaction = current
    if transaction.status not in (TransactionStatus.CONFIRMED, TransactionStatus.REVERTED):
        transaction.mark_outcome_unknown(raw_error)


def _record_broadcast(swap_order, tx_record, tx_hash):
    current = _record_sent(swap_order, tx_record, tx_hash)
    if current is None:
        return tx_hash
    swap, transaction = current
    try:
        receipt = get_base_chain_client().receipt_even_if_reverted(tx_hash)
    except Exception:
        logger.warning("Swap %s has a recorded broadcast and no receipt yet", swap.uuid)
        return tx_hash
    _record_receipt(swap, transaction, tx_hash, receipt)
    return tx_hash


@atomic()
def _record_sent(swap_order, tx_record, tx_hash):
    current = lock_current_claim(swap_order, tx_record)
    if current is None or not hash_identity(tx_hash):
        return None
    swap, transaction = current
    if transaction.tx_hash and hash_identity(transaction.tx_hash) != hash_identity(tx_hash):
        return None
    if transaction.status in (TransactionStatus.CONFIRMED, TransactionStatus.REVERTED):
        return current if transaction.tx_hash else None
    if transaction.status != TransactionStatus.SUBMITTED or not transaction.tx_hash:
        transaction.mark_submitted(tx_hash)
    if not swap.tx_hash:
        swap.mark_executing(tx_hash, transaction=transaction)
    return swap, transaction


@atomic()
def _record_receipt(swap_order, tx_record, tx_hash, receipt):
    if not isinstance(receipt, Mapping) or receipt.get("status") not in (0, 1):
        return None
    if not hash_identity(tx_hash):
        return None
    receipt_hash = receipt.get("transactionHash")
    if receipt_hash is not None and hash_identity(receipt_hash) != hash_identity(tx_hash):
        return None
    current = lock_current_claim(swap_order, tx_record, with_orders=True)
    if current is None:
        return None
    swap, transaction = current
    if hash_identity(transaction.tx_hash) != hash_identity(tx_hash):
        return None
    if receipt["status"] == 1:
        if transaction.status == TransactionStatus.REVERTED:
            return None
        if transaction.status != TransactionStatus.CONFIRMED:
            block_hash = receipt.get("blockHash", "")
            transaction.mark_confirmed(
                block_number=receipt.get("blockNumber"),
                block_hash=block_hash.hex() if isinstance(block_hash, bytes) else block_hash,
                gas_used=receipt.get("gasUsed"),
            )
        swap.mark_completed()
        publish_trading_event("swap_completed", str(swap.share_token_id))
        return "executed"
    if transaction.status == TransactionStatus.CONFIRMED:
        return None
    reason = f"The chain reverted the swap: {tx_hash}"
    if transaction.status != TransactionStatus.REVERTED:
        transaction.mark_reverted(reason)
    swap.mark_failed(reason)
    publish_trading_event("swap_failed", str(swap.share_token_id))
    return "reverted"


def executed_order_hash(swap_order: SwapOrder) -> str:
    signable = encode_typed_data(full_message=get_typed_data(swap_order))
    return _hash_eip191_message(signable).hex()


def chain_says_this_swap_executed(swap_order: SwapOrder, receipt=None) -> bool:
    if swap_order.settlement_protocol_version == 0 or not swap_order.tx_hash:
        return False
    recorded = recorded_settlement_context(swap_order)
    if receipt is None:
        receipt = get_base_chain_client().receipt_even_if_reverted(swap_order.tx_hash)
    if not isinstance(receipt, Mapping) or receipt.get("status") != 1:
        return False
    if get_base_chain_client().w3.eth.chain_id != int(recorded["typed_data"]["domain"]["chainId"]):
        return False
    contract = get_base_chain_client().load_contract("AtomicSwap", settlement_contract(swap_order))
    expected = executed_order_hash(swap_order)
    for event in contract.events.SwapExecuted().process_receipt(receipt):
        if hash_identity(event["args"]["orderHash"]) == hash_identity(expected):
            return True
    return False


def resolve_executing_swap(swap_order: SwapOrder) -> Optional[str]:
    if swap_order.settlement_protocol_version == 0:
        return None
    recorded_settlement_context(swap_order)
    if swap_order.status != SwapOrderStatus.EXECUTING or not swap_order.transaction_id or not swap_order.tx_hash:
        return None
    transaction = BlockchainTransaction.objects.get(pk=swap_order.transaction_id)
    if hash_identity(transaction.tx_hash) != hash_identity(swap_order.tx_hash):
        return None
    receipt = get_base_chain_client().receipt_even_if_reverted(swap_order.tx_hash)
    if isinstance(receipt, Mapping) and receipt.get("status") == 1:
        if not chain_says_this_swap_executed(swap_order, receipt):
            return None
    return _record_receipt(swap_order, transaction, swap_order.tx_hash, receipt)


def sign_and_execute_swap(swap_order, signature: str, signer_address: str, admission=None):
    with use_operator():
        signed = submit_signature(
            swap_order=swap_order, signature=signature, signer_address=signer_address, admission=admission
        )

        if signed.is_ready:
            logger.info(f"Both signatures present, executing swap {signed.uuid}")
            execute_swap(signed, admission=admission)
            signed.refresh_from_db()

    return signed


def _signature_bytes(signature: str) -> bytes:
    return bytes.fromhex(signature[2:] if signature.startswith("0x") else signature)
