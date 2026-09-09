import re
from uuid import uuid4

from django.db import connections
from django.utils import timezone
from web3 import Web3

from shared.db import atomic
from shared.db.aliases import current_alias
from tokens.exceptions import InvalidTokenStateException
from tokens.models import (
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
)

LEGACY_MINT_UNIDENTIFIED = (
    "This legacy issuance has no recorded transaction identity. An operator must identify its mint "
    "before execution can continue. A missing transaction or receipt does not prove that nothing was sent."
)
ATTEMPT_SUPERSEDED = "This mint attempt is no longer current. Resolve the current issuance before retrying."


def mint_failure_detail(error):
    return re.sub(r"(?:0x)?[0-9a-f]{132,}", "[signed transaction redacted]", str(error), flags=re.IGNORECASE)


def require_commit_boundary():
    connection = connections[current_alias()]
    if not connection.get_autocommit() and not connection.in_atomic_block:
        raise RuntimeError("Mint signing requires autocommit so its journal is durable before broadcast.")


def start_mint_attempt(request, issuance, **issuance_fields):
    require_commit_boundary()
    with atomic(durable=True):
        request = ShareIssuanceRequest.objects.select_for_update().get(pk=request.pk)
        try:
            request.mark_executing()
        except ValueError as exc:
            raise InvalidTokenStateException(
                f"Cannot execute request with status '{request.get_status_display()}'"
            ) from exc
        if issuance is not None:
            issuance = ShareIssuance.objects.select_for_update().get(pk=issuance.pk)
            if issuance.tx_hash or issuance.status == IssuanceStatus.COMPLETED:
                raise InvalidTokenStateException(ATTEMPT_SUPERSEDED)
            if issuance.mint_journal is None:
                raise InvalidTokenStateException(LEGACY_MINT_UNIDENTIFIED)
            if (
                issuance.mint_journal
                and issuance.mint_journal[-1].get("tx_hash")
                and not issuance.mint_journal[-1].get("reverted")
            ):
                raise InvalidTokenStateException(ATTEMPT_SUPERSEDED)
        if issuance is None:
            issuance = ShareIssuance.objects.create(mint_journal=[], **issuance_fields)
        attempt_id = str(uuid4())
        issuance.mint_journal = [*issuance.mint_journal, {"id": attempt_id}]
        issuance.save(update_fields=["mint_journal", "updated_at"])
        issuance.mark_processing()
    return issuance, attempt_id


def record_signed_mint(request, issuance, attempt_id, tx_hash, raw_transaction):
    if Web3.to_hex(Web3.keccak(raw_transaction)) != tx_hash:
        raise InvalidTokenStateException("The signed mint does not match its transaction hash.")
    require_commit_boundary()
    with atomic(durable=True):
        current_request = ShareIssuanceRequest.objects.select_for_update().get(pk=request.pk)
        current = ShareIssuance.objects.select_for_update().get(pk=issuance.pk)
        journal = current.mint_journal
        if (
            current_request.status != RequestStatus.EXECUTING
            or not journal
            or journal[-1] != {"id": attempt_id}
            or current.tx_hash
        ):
            raise InvalidTokenStateException(ATTEMPT_SUPERSEDED)
        journal[-1] = {
            "id": attempt_id,
            "tx_hash": tx_hash,
            "raw_transaction": Web3.to_hex(raw_transaction),
            "signed_at": timezone.now().isoformat(),
        }
        current.tx_hash = tx_hash
        current.save(update_fields=["tx_hash", "mint_journal", "updated_at"])
    issuance.tx_hash = current.tx_hash
    issuance.mint_journal = current.mint_journal


def recorded_mint_payload(issuance):
    if issuance.mint_journal is None:
        return None
    journal = issuance.mint_journal
    if not journal or journal[-1].get("tx_hash") != issuance.tx_hash:
        raise InvalidTokenStateException("The mint journal does not identify the current transaction.")
    try:
        raw_transaction = Web3.to_bytes(hexstr=journal[-1]["raw_transaction"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenStateException("The mint journal has no valid signed transaction.") from exc
    if Web3.to_hex(Web3.keccak(raw_transaction)) != issuance.tx_hash:
        raise InvalidTokenStateException("The mint journal payload does not match its transaction hash.")
    return raw_transaction


def fail_mint_attempt(request, issuance, attempt_id, error_message, request_error):
    with atomic():
        current_request = ShareIssuanceRequest.objects.select_for_update().get(pk=request.pk)
        current = ShareIssuance.objects.select_for_update().get(pk=issuance.pk)
        if (
            current_request.status != RequestStatus.EXECUTING
            or not current.mint_journal
            or current.mint_journal[-1].get("id") != attempt_id
            or current.mint_journal[-1].get("abandoned")
        ):
            return
        current.mark_failed(error_message)
        current_request.mark_failed(request_error)


def fail_recorded_mint(request, issuance, tx_hash, error_message, request_error):
    with atomic():
        current_request = ShareIssuanceRequest.objects.select_for_update().get(pk=request.pk)
        current = ShareIssuance.objects.select_for_update().get(pk=issuance.pk)
        if (
            current_request.status == RequestStatus.EXECUTED
            or current.status == IssuanceStatus.COMPLETED
            or current.tx_hash != tx_hash
        ):
            return
        current.mark_failed(error_message)
        current_request.mark_failed(request_error)


def release_unsigned_mint(request, reason):
    require_commit_boundary()
    with atomic(durable=True):
        current_request = ShareIssuanceRequest.objects.select_for_update().get(pk=request.pk)
        current = (
            ShareIssuance.objects.select_for_update().filter(idempotency_key=f"issuance-request:{request.uuid}").first()
        )
        if current_request.status != RequestStatus.EXECUTING:
            return False
        if current is not None:
            if current.tx_hash or not current.mint_journal or current.status == IssuanceStatus.COMPLETED:
                return False
            attempt = current.mint_journal[-1]
            if set(attempt) != {"id"}:
                return False
            attempt["abandoned"] = True
            current.save(update_fields=["mint_journal", "updated_at"])
            current.mark_failed(reason)
        current_request.mark_failed(reason)
    return True


def mark_mint_reverted(request, issuance, tx_hash, *, fail_request=False):
    with atomic():
        current_request = ShareIssuanceRequest.objects.select_for_update().get(pk=request.pk)
        current = ShareIssuance.objects.select_for_update().get(pk=issuance.pk)
        if current.tx_hash != tx_hash or current.status == IssuanceStatus.COMPLETED:
            raise InvalidTokenStateException(ATTEMPT_SUPERSEDED)
        if current.mint_journal is None:
            current.mint_journal = [{"tx_hash": tx_hash, "reverted": True}]
        else:
            current.mint_journal[-1]["reverted"] = True
        current.save(update_fields=["mint_journal", "updated_at"])
        current.mark_reverted(f"Transaction reverted: {tx_hash}")
        if fail_request:
            current_request.mark_failed(f"Transaction reverted: {tx_hash}")
