from dataclasses import dataclass
from uuid import UUID, uuid4

from django.db import connections
from django.utils import timezone
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction as LegacyTransaction
from web3 import Web3

from blockchain.models import (
    OutgoingOperation,
    OutgoingStatus,
    SignedAttempt,
    SigningAccount,
)
from shared.db import APP_ALIAS, atomic, current_alias

MAX_DATABASE_INTEGER = 2**63 - 1
MAX_TRANSACTION_VALUE = 2**256 - 1
STALE_ATTEMPT = "This outgoing transaction attempt is no longer current."
OPERATOR_REQUIRED = "Outgoing transaction storage requires an operator connection."


class OutgoingTransactionError(ValueError):
    pass


@dataclass(frozen=True)
class OperationClaim:
    operation_id: UUID
    claim_id: UUID


@dataclass(frozen=True)
class PreparedTransaction:
    claim: OperationClaim
    chain_id: int
    sender: str
    to: str | None
    value: int
    data: str
    observed_nonce: int
    gas: int
    gas_price: int


@dataclass(frozen=True)
class BroadcastResult:
    tx_hash: str
    acknowledged: bool


def _boundary():
    if current_alias() == APP_ALIAS:
        raise OutgoingTransactionError(OPERATOR_REQUIRED)
    connection = connections[current_alias()]
    if not connection.get_autocommit() or connection.in_atomic_block:
        raise OutgoingTransactionError("Outgoing transactions require autocommit outside every transaction block.")


def _integer(value, maximum=MAX_DATABASE_INTEGER):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise OutgoingTransactionError("A transaction integer is outside the supported range.")
    return value


def _address(value):
    if not isinstance(value, str) or not Web3.is_address(value):
        raise OutgoingTransactionError("A transaction address is invalid.")
    return Web3.to_checksum_address(value).lower()


def _hex(value, length=None):
    try:
        if isinstance(value, str):
            raw = bytes.fromhex(value.removeprefix("0x"))
        elif isinstance(value, (bytes, bytearray, memoryview)):
            raw = bytes(value)
        else:
            raise ValueError
    except (TypeError, ValueError):
        raise OutgoingTransactionError("A transaction hexadecimal value is invalid.") from None
    if length is not None and len(raw) != length:
        raise OutgoingTransactionError("A transaction hexadecimal value has the wrong length.")
    return Web3.to_hex(raw)


def transaction_intent(*, chain_id, sender, to, value=0, data="0x"):
    if _integer(chain_id) == 0:
        raise OutgoingTransactionError("The transaction must name a chain.")
    return {
        "chain_id": chain_id,
        "sender": _address(sender),
        "to": _address(to) if to is not None else None,
        "value": str(_integer(value, MAX_TRANSACTION_VALUE)),
        "data": _hex(data),
    }


def open_operation(operation_key, *, chain_id, sender, to, value=0, data="0x"):
    _boundary()
    if not isinstance(operation_key, str) or not operation_key.strip() or len(operation_key) > 200:
        raise OutgoingTransactionError("An outgoing operation requires a stable key of at most 200 characters.")
    intent = transaction_intent(chain_id=chain_id, sender=sender, to=to, value=value, data=data)
    with atomic(durable=True):
        operation, _ = OutgoingOperation.objects.get_or_create(
            operation_key=operation_key, defaults={"intent": intent, "claim_id": uuid4()}
        )
        operation = OutgoingOperation.objects.select_for_update().get(pk=operation.pk)
        if operation.intent != intent:
            raise OutgoingTransactionError("This outgoing operation key already identifies a different intent.")
        if operation.status in (OutgoingStatus.FAILED, OutgoingStatus.REVERTED):
            operation.claim_id = uuid4()
            operation.current_attempt = None
            operation.status = OutgoingStatus.PREPARING
            operation.last_error = ""
            operation.acknowledged_at = None
            operation.block_number = None
            operation.block_hash = ""
            operation.gas_used = None
            operation.save(
                update_fields=[
                    "claim_id",
                    "current_attempt",
                    "status",
                    "last_error",
                    "acknowledged_at",
                    "block_number",
                    "block_hash",
                    "gas_used",
                    "updated_at",
                ]
            )
    return OperationClaim(operation.pk, operation.claim_id)


def _current(claim, *, lock=False):
    queryset = OutgoingOperation.objects.select_for_update() if lock else OutgoingOperation.objects
    operation = queryset.get(pk=claim.operation_id)
    if operation.claim_id != claim.claim_id:
        raise OutgoingTransactionError(STALE_ATTEMPT)
    return operation


def prepare_operation(claim, client):
    _boundary()
    operation = _current(claim)
    if operation.status != OutgoingStatus.PREPARING:
        raise OutgoingTransactionError("This operation has no transaction to prepare.")
    intent = operation.intent
    try:
        if client.assert_expected_chain() != intent["chain_id"]:
            raise OutgoingTransactionError("The endpoint is on a different chain from the outgoing intent.")
        nonce = _integer(client.get_nonce(intent["sender"]), MAX_DATABASE_INTEGER - 1)
        gas_price = _integer(client.gas_price, MAX_TRANSACTION_VALUE)
        transaction = {
            "chainId": intent["chain_id"],
            "from": Web3.to_checksum_address(intent["sender"]),
            "value": int(intent["value"]),
            "data": intent["data"],
            "nonce": nonce,
            "gasPrice": gas_price,
        }
        if intent["to"] is not None:
            transaction["to"] = Web3.to_checksum_address(intent["to"])
        gas = _integer(client.estimate_gas(transaction))
        if gas == 0:
            raise OutgoingTransactionError("The transaction gas limit must be positive.")
    except OutgoingTransactionError:
        raise
    except Exception:
        raise OutgoingTransactionError("The outgoing transaction could not be prepared.") from None
    return PreparedTransaction(
        claim,
        intent["chain_id"],
        intent["sender"],
        intent["to"],
        int(intent["value"]),
        intent["data"],
        nonce,
        gas,
        gas_price,
    )


def sign_operation(claim, prepared, private_key):
    _boundary()
    if prepared.claim != claim:
        raise OutgoingTransactionError(STALE_ATTEMPT)
    try:
        account = Account.from_key(private_key)
    except Exception:
        raise OutgoingTransactionError("The outgoing signer key is invalid.") from None
    intent = transaction_intent(
        chain_id=prepared.chain_id, sender=prepared.sender, to=prepared.to, value=prepared.value, data=prepared.data
    )
    if account.address.lower() != intent["sender"]:
        raise OutgoingTransactionError("The signing key does not belong to the outgoing sender.")
    _integer(prepared.observed_nonce, MAX_DATABASE_INTEGER - 1)
    _integer(prepared.gas_price, MAX_TRANSACTION_VALUE)
    if _integer(prepared.gas) == 0:
        raise OutgoingTransactionError("The transaction gas limit must be positive.")
    try:
        with atomic(durable=True):
            operation = _current(claim, lock=True)
            if operation.intent != intent:
                raise OutgoingTransactionError("The prepared transaction differs from the outgoing intent.")
            if operation.status in (OutgoingStatus.SIGNED, OutgoingStatus.CONFIRMED):
                return operation.current_attempt
            if operation.status != OutgoingStatus.PREPARING:
                raise OutgoingTransactionError(STALE_ATTEMPT)
            signer, _ = SigningAccount.objects.get_or_create(chain_id=prepared.chain_id, address=intent["sender"])
            signer = SigningAccount.objects.select_for_update().get(pk=signer.pk)
            nonce = _integer(max(signer.next_nonce, prepared.observed_nonce), MAX_DATABASE_INTEGER - 1)
            transaction = {
                "chainId": prepared.chain_id,
                "nonce": nonce,
                "value": prepared.value,
                "data": prepared.data,
                "gas": prepared.gas,
                "gasPrice": prepared.gas_price,
            }
            if prepared.to is not None:
                transaction["to"] = Web3.to_checksum_address(prepared.to)
            try:
                raw = bytes(account.sign_transaction(transaction).raw_transaction)
            except Exception:
                raise OutgoingTransactionError("The outgoing transaction could not be signed locally.") from None
            attempt = SignedAttempt.objects.create(
                operation=operation,
                claim_id=claim.claim_id,
                signer=signer,
                nonce=nonce,
                tx_hash=Web3.to_hex(Web3.keccak(raw)),
                raw_transaction=raw,
            )
            signer.next_nonce = nonce + 1
            signer.save(update_fields=["next_nonce", "updated_at"])
            operation.current_attempt = attempt
            operation.status = OutgoingStatus.SIGNED
            operation.save(update_fields=["current_attempt", "status", "updated_at"])
    except OutgoingTransactionError:
        raise
    except Exception:
        raise OutgoingTransactionError("The signed outgoing transaction could not be committed.") from None
    return attempt


def fail_preparing(claim):
    _boundary()
    with atomic(durable=True):
        operation = OutgoingOperation.objects.select_for_update().get(pk=claim.operation_id)
        if operation.claim_id != claim.claim_id or operation.status != OutgoingStatus.PREPARING:
            return False
        operation.status = OutgoingStatus.FAILED
        operation.save(update_fields=["status", "updated_at"])
    return True


def _payload(operation):
    attempt = operation.current_attempt
    if attempt is None or attempt.operation_id != operation.pk or attempt.claim_id != operation.claim_id:
        raise OutgoingTransactionError("The outgoing operation has no matching signed attempt.")
    raw = bytes(attempt.raw_transaction)
    if Web3.to_hex(Web3.keccak(raw)) != attempt.tx_hash:
        raise OutgoingTransactionError("The outgoing signed payload does not match its recorded hash.")
    try:
        fields = LegacyTransaction.from_bytes(raw).as_dict()
        decoded = transaction_intent(
            chain_id=(fields["v"] - 35) // 2,
            sender=Account.recover_transaction(raw),
            to=Web3.to_checksum_address(fields["to"]) if fields["to"] else None,
            value=fields["value"],
            data=fields["data"],
        )
    except Exception:
        raise OutgoingTransactionError("The outgoing signed payload cannot be verified.") from None
    if (
        decoded != operation.intent
        or fields["nonce"] != attempt.nonce
        or attempt.signer.chain_id != decoded["chain_id"]
        or attempt.signer.address != decoded["sender"]
    ):
        raise OutgoingTransactionError("The outgoing signed payload differs from its recorded intent or nonce.")
    return attempt, raw


def _record_broadcast(claim, tx_hash, error):
    with atomic(durable=True):
        operation = OutgoingOperation.objects.select_for_update().get(pk=claim.operation_id)
        if operation.claim_id != claim.claim_id or operation.status != OutgoingStatus.SIGNED:
            return
        attempt, _ = _payload(operation)
        if attempt.tx_hash != tx_hash:
            return
        operation.last_error = error
        if not error:
            operation.acknowledged_at = timezone.now()
        operation.save(update_fields=["last_error", "acknowledged_at", "updated_at"])


def broadcast_operation(claim, client):
    _boundary()
    operation = _current(claim)
    attempt, raw = _payload(operation)
    if operation.status == OutgoingStatus.CONFIRMED:
        return BroadcastResult(attempt.tx_hash, True)
    if operation.status != OutgoingStatus.SIGNED:
        raise OutgoingTransactionError(STALE_ATTEMPT)
    error = ""
    try:
        if client.assert_expected_chain() != operation.intent["chain_id"]:
            raise OutgoingTransactionError("The endpoint is on a different chain from the outgoing intent.")
        if _hex(client.send_raw_transaction(raw), 32) != attempt.tx_hash:
            error = "UnexpectedTransactionHash"
    except Exception as exc:
        error = type(exc).__name__[:100]
    _record_broadcast(claim, attempt.tx_hash, error)
    return BroadcastResult(attempt.tx_hash, not error)


def record_receipt(claim, tx_hash, receipt):
    _boundary()
    tx_hash = _hex(tx_hash, 32)
    if _hex(receipt["transactionHash"], 32) != tx_hash:
        raise OutgoingTransactionError("The receipt identifies a different transaction.")
    status = _integer(receipt["status"], 1)
    block_number = _integer(receipt["blockNumber"])
    block_hash = _hex(receipt["blockHash"], 32)
    gas_used = _integer(receipt["gasUsed"])
    with atomic(durable=True):
        operation = OutgoingOperation.objects.select_for_update().get(pk=claim.operation_id)
        if operation.claim_id != claim.claim_id or operation.status != OutgoingStatus.SIGNED:
            return False
        attempt, _ = _payload(operation)
        if attempt.tx_hash != tx_hash:
            return False
        operation.status = OutgoingStatus.CONFIRMED if status == 1 else OutgoingStatus.REVERTED
        operation.block_number = block_number
        operation.block_hash = block_hash
        operation.gas_used = gas_used
        operation.last_error = ""
        operation.save(update_fields=["status", "block_number", "block_hash", "gas_used", "last_error", "updated_at"])
    return True


def reconcile_operation(claim, client):
    _boundary()
    operation = _current(claim)
    attempt, _ = _payload(operation)
    if operation.status != OutgoingStatus.SIGNED:
        return False
    try:
        if client.assert_expected_chain() != operation.intent["chain_id"]:
            raise OutgoingTransactionError("The endpoint is on a different chain from the outgoing intent.")
        receipt = client.get_transaction_receipt(attempt.tx_hash)
    except Exception:
        return False
    if receipt is None:
        return False
    return record_receipt(claim, attempt.tx_hash, receipt)
