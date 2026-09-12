import logging
from collections.abc import Mapping
from decimal import Decimal

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from integrations.blockchain import get_blockchain_client
from integrations.blockchain.bitcoin_transactions import decode_bitcoin_transaction
from integrations.blockchain.receipts import transaction_hash_matches
from shared.constants import normalize_chain
from shared.db import atomic
from wallets.exceptions import BlockchainAPIError, InvalidTransactionException
from wallets.models import (
    BitcoinSubmission,
    BitcoinSubmissionInput,
    Holding,
    Transaction,
    Wallet,
)
from wallets.services import transaction_confirmation
from wallets.services.bitcoin_intent import (
    GENESIS_HASHES,
    bitcoin_transfer_outputs,
    check_bitcoin_admission,
    observe_bitcoin_inputs,
    prepare_bitcoin_intent,
    verified_bitcoin_network,
)

logger = logging.getLogger(__name__)


def _decode(raw):
    try:
        return decode_bitcoin_transaction(raw)
    except (ValueError, TypeError):
        raise InvalidTransactionException("The signed Bitcoin transaction could not be decoded.") from None


def _wallet_context(wallet):
    return wallet.pk, wallet.user_account_id, wallet.chain, wallet.address


def _request_wallet(wallet_id, principal_id, *, lock=False):
    query = Wallet.objects.filter(pk=wallet_id, user_account__user_profiles__user_id=principal_id)
    if lock:
        query = query.select_for_update(of=("self",))
    wallet = query.first()
    if wallet is None or normalize_chain(wallet.chain) != "bitcoin" or wallet.verification_status != "VERIFIED":
        raise InvalidTransactionException("A verified Bitcoin wallet belonging to the requesting user is required.")
    return wallet


def submit_bitcoin_transfer(wallet, raw, *, principal_id):
    if principal_id is None:
        raise InvalidTransactionException("A Bitcoin submission requires its requesting user.")
    decoded = _decode(raw)
    observed_wallet = _request_wallet(wallet.pk, principal_id)
    existing = BitcoinSubmission.objects.filter(wallet=observed_wallet, tx_hash=decoded.tx_hash).first()
    intent = None
    preparation_error = None
    if existing is None:
        try:
            intent = prepare_bitcoin_intent(get_blockchain_client("bitcoin"), decoded, observed_wallet)
        except InvalidTransactionException as exc:
            preparation_error = exc
        except Exception:
            preparation_error = BlockchainAPIError("Bitcoin input and signature verification is unavailable.")
    try:
        with atomic(durable=True):
            locked_wallet = _request_wallet(wallet.pk, principal_id, lock=True)
            submission = BitcoinSubmission.objects.filter(wallet=locked_wallet, tx_hash=decoded.tx_hash).first()
            if submission is not None:
                if bytes(submission.raw_transaction) != decoded.raw:
                    raise InvalidTransactionException(
                        "Different Bitcoin witness bytes are already recorded for this transaction."
                    )
            else:
                if preparation_error is not None:
                    raise preparation_error
                if intent is None or _wallet_context(locked_wallet) != _wallet_context(observed_wallet):
                    raise InvalidTransactionException(
                        "The Bitcoin wallet changed during input verification; submit again."
                    )
                submission = _record_submission(locked_wallet, decoded, intent)
    except IntegrityError:
        raise InvalidTransactionException("This Bitcoin identity or one of its inputs is already recorded.") from None
    attempt_bitcoin_submission(submission.pk)
    tx = Transaction.objects.get(pk=submission.transaction_id)
    quantity = Holding.objects.filter(wallet=tx.wallet, asset=tx.asset).values_list("quantity", flat=True).first()
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


def _record_submission(wallet, decoded, intent):
    if Transaction.objects.filter(wallet=wallet, tx_hash=decoded.tx_hash).exists():
        raise InvalidTransactionException("This Bitcoin transaction has history without a signed submission record.")
    if BitcoinSubmission.objects.filter(wallet=wallet).exclude(network=intent["network"]).exists():
        raise InvalidTransactionException("This wallet already has a recorded Bitcoin network.")
    result = transaction_confirmation.create_pending_transaction(
        wallet,
        decoded.tx_hash,
        intent["to_address"],
        Decimal(intent["amount_satoshis"]).scaleb(-8),
        transaction_fee=Decimal(intent["fee_satoshis"]).scaleb(-8),
    )
    tx = Transaction.objects.get(pk=result["transaction_id"])
    submission = BitcoinSubmission.objects.create(
        wallet=wallet,
        user_account_id=wallet.user_account_id,
        transaction=tx,
        asset_id=tx.asset_id,
        network=intent["network"],
        genesis_hash=intent["genesis_hash"],
        sender_address=wallet.address,
        tx_hash=decoded.tx_hash,
        witness_hash=decoded.witness_hash,
        raw_transaction=decoded.raw,
        intent=intent,
    )
    BitcoinSubmissionInput.objects.bulk_create(
        [
            BitcoinSubmissionInput(
                submission=submission,
                user_account_id=wallet.user_account_id,
                network=submission.network,
                previous_tx_hash=item["tx_hash"],
                output_index=item["output_index"],
                satoshis=item["satoshis"],
                script=bytes.fromhex(item["script"]),
                observed_block_hash=item["observed_block_hash"],
            )
            for item in sorted(intent["inputs"], key=lambda item: (item["tx_hash"], item["output_index"]))
        ]
    )
    return submission


def _recorded_inputs(submission, decoded):
    inputs = list(submission.inputs.all())
    if any(item.user_account_id != submission.user_account_id or item.network != submission.network for item in inputs):
        raise InvalidTransactionException("A recorded Bitcoin input has a different owner or network.")
    recorded = {
        (item.previous_tx_hash, item.output_index): (item.satoshis, bytes(item.script).hex()) for item in inputs
    }
    intent = {
        (item["tx_hash"], item["output_index"]): (item["satoshis"], item["script"])
        for item in submission.intent["inputs"]
    }
    if recorded != intent or set(recorded) != {(item.tx_hash, item.output_index) for item in decoded.inputs}:
        raise InvalidTransactionException("The recorded Bitcoin inputs do not match the signed intent.")
    return recorded


def attempt_bitcoin_submission(submission_id):
    submission = BitcoinSubmission.objects.select_related("wallet", "transaction").filter(pk=submission_id).first()
    if submission is None:
        return "not_found"
    if submission.transaction.status != "pending":
        return "already_processed"
    now = timezone.now()
    BitcoinSubmission.objects.filter(pk=submission.pk).filter(
        Q(last_attempt_at__isnull=True) | Q(last_attempt_at__lte=now)
    ).update(last_attempt_at=now, updated_at=now)
    try:
        decoded = _decode(bytes(submission.raw_transaction))
        if (
            decoded.tx_hash != submission.tx_hash
            or decoded.witness_hash != submission.witness_hash
            or submission.wallet.user_account_id != submission.user_account_id
            or submission.wallet.address != submission.sender_address
            or normalize_chain(submission.wallet.chain) != "bitcoin"
            or GENESIS_HASHES.get(submission.network) != submission.genesis_hash
        ):
            return "identity_unavailable"
        sender_script, recipient, amount = bitcoin_transfer_outputs(
            decoded, submission.sender_address, submission.network
        )
        recorded = _recorded_inputs(submission, decoded)
        fee = sum(value[0] for value in recorded.values()) - sum(output.satoshis for output in decoded.outputs)
        if (
            recipient != submission.intent["to_address"]
            or amount != submission.intent["amount_satoshis"]
            or fee < 0
            or fee != submission.intent["fee_satoshis"]
            or any(value[1] != sender_script.hex() for value in recorded.values())
            or submission.intent["network"] != submission.network
            or submission.intent["genesis_hash"] != submission.genesis_hash
            or submission.intent["sender_address"] != submission.sender_address
            or submission.intent["version"] != decoded.version
            or submission.intent["lock_time"] != decoded.lock_time
            or submission.intent["outputs"]
            != [{"satoshis": output.satoshis, "script": output.script.hex()} for output in decoded.outputs]
        ):
            return "identity_unavailable"
        tx = submission.transaction
        if (
            tx.wallet_id != submission.wallet_id
            or tx.user_account_id != submission.user_account_id
            or tx.asset_id != submission.asset_id
            or tx.tx_hash != submission.tx_hash
            or normalize_chain(tx.chain) != "bitcoin"
            or tx.from_address != submission.sender_address
            or tx.to_address != recipient
            or tx.amount != Decimal(amount).scaleb(-8)
            or tx.transaction_fee_estimated != Decimal(fee).scaleb(-8)
            or tx.nonce is not None
            or tx.imported_from_history
        ):
            return "identity_unavailable"
        client = get_blockchain_client("bitcoin")
        verified_bitcoin_network(client, submission.network)
        receipt = client.get_transaction_receipt(submission.tx_hash)
        if receipt is not None:
            if isinstance(receipt, Mapping) and transaction_hash_matches(receipt.get("tx_hash"), submission.tx_hash):
                return "receipt_available"
            return "receipt_identity_unavailable"
        current = observe_bitcoin_inputs(client, decoded, sender_script)
        if {
            (item["tx_hash"], item["output_index"]): (item["satoshis"], item["script"]) for item in current
        } != recorded:
            return "input_identity_unavailable"
        admission = check_bitcoin_admission(client, decoded, fee, allow_known=True)
        verified_bitcoin_network(client, submission.network)
        if admission == "allowed":
            acknowledged = client.broadcast_transaction(decoded.raw.hex())
            if not transaction_hash_matches(acknowledged, submission.tx_hash):
                return "acknowledgement_unavailable"
    except Exception:
        logger.warning("Bitcoin submission delivery remains unresolved")
        return "delivery_unavailable"
    BitcoinSubmission.objects.filter(pk=submission.pk, acknowledged_at__isnull=True).update(
        acknowledged_at=timezone.now(), updated_at=timezone.now()
    )
    return "acknowledged"
