import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import connections
from django.utils import timezone
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction
from eth_keys.constants import SECPK1_N
from web3 import Web3

from blockchain.models import (
    OutgoingCutoverHold,
    OutgoingHistoryCapture,
    OutgoingHistoryEvidence,
)
from shared.db import APP_ALIAS, atomic, current_alias
from tokens.services.legacy_outgoing_sources import read_legacy_outgoing_sources

VALIDATOR_VERSION = "legacy-operator-v1"
COVERAGE_LIMITS = ("unjournaled_pause_and_approval", "offline_and_old_signers_not_observed")
SCOPE = {"source_set": "legacy_operator", "coverage_limits": list(COVERAGE_LIMITS)}
INVENTORY_LOCK = 78035948123465201
MAX_UINT256 = 2**256 - 1


class OutgoingInventoryError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class InventorySnapshot:
    snapshot_at: datetime
    sources: tuple


def require_inventory_boundary():
    if current_alias() == APP_ALIAS:
        raise OutgoingInventoryError("Outgoing history inventory requires an operator connection.")
    connection = connections[current_alias()]
    if not connection.get_autocommit() or connection.in_atomic_block:
        raise OutgoingInventoryError("Outgoing history inventory requires autocommit outside every transaction block.")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def collect_inventory():
    require_inventory_boundary()
    try:
        with atomic():
            connection = connections[current_alias()]
            if connection.vendor == "postgresql":
                with connections[current_alias()].cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            moment = timezone.now()
            sources = read_legacy_outgoing_sources()
    except Exception:
        raise OutgoingInventoryError("The outgoing history snapshot could not be collected.") from None
    return InventorySnapshot(moment, sources)


def _manifest(snapshot):
    sources = sorted(
        (source["model"], source["uuid"], source["entry_key"], _digest(source)) for source in snapshot.sources
    )
    return _digest({"validator_version": VALIDATOR_VERSION, "scope": SCOPE, "sources": sources})


def _address(value):
    return value.lower() if isinstance(value, str) and Web3.is_address(value) else None


def _claimed_hash(value):
    return value.lower() if isinstance(value, str) else None


def _uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (TypeError, ValueError):
        return False


def _mint_source(source, evidence):
    row, token = source["row"], source["token"] or {}
    candidates = source["request_candidates"]
    request = candidates[0] if len(candidates) == 1 else {}
    try:
        amount = int(row["amount"])
        valid_amount = 0 < amount <= MAX_UINT256 and amount == request.get("amount")
    except (TypeError, ValueError):
        amount, valid_amount = None, False
    evidence.expected_terms = {
        "to": _address(token.get("contract_address")),
        "recipient": _address(row["recipient_address"]),
        "amount": str(amount) if amount is not None else None,
        "value": "0",
        "function": "mint(address,uint256)",
    }
    evidence.source_link_valid = bool(
        request
        and row["idempotency_key"] == f"issuance-request:{request['uuid']}"
        and not source["capital_links"]
        and request["executed_issuance_id"] in (None, row["uuid"])
        and row["token_id"] == request["token_id"] == token.get("uuid")
        and token.get("decimals") == 0
        and evidence.expected_terms["recipient"] is not None
        and evidence.expected_terms["recipient"] == _address(request["recipient_address"])
        and valid_amount
    )
    if evidence.source_link_valid:
        evidence.operation_key = f"issuance-request:{request['uuid']}"
    else:
        evidence.findings.append("invalid_source_link")
    entry = source["journal_entry"]
    if source["journal_shape"] == "invalid" or (source["journal_shape"] == "entries" and not isinstance(entry, dict)):
        evidence.findings.append("malformed_journal")
    entry = entry or {}
    valid_id = source["attempt_id_unique"] and _uuid(entry.get("id"))
    if not valid_id:
        evidence.findings.append("invalid_attempt_identity")
    unsigned_shape = source["entry_keys"] == ["id"] or (
        source["entry_keys"] == ["abandoned", "id"] and entry.get("abandoned") is True
    )
    evidence.proved_unsigned = bool(
        valid_id
        and unsigned_shape
        and evidence.source_link_valid
        and (not source["is_current_entry"] or not row["tx_hash"])
    )
    if evidence.proved_unsigned:
        if not entry.get("abandoned"):
            evidence.findings.append("unsigned_inflight_snapshot")
        return
    _decode(entry.get("raw_transaction"), evidence)
    if evidence.observed_hash and _claimed_hash(entry.get("tx_hash")) != evidence.observed_hash:
        evidence.findings.append("recorded_hash_mismatch")
    if source["is_current_entry"] and not entry.get("reverted") and row["tx_hash"] != entry.get("tx_hash"):
        evidence.findings.append("current_hash_mismatch")
    if evidence.raw_valid:
        expected = evidence.expected_terms
        if (
            expected["recipient"]
            and expected["amount"]
            and expected["to"]
            and amount is not None
            and 0 <= amount <= MAX_UINT256
        ):
            data = Web3.to_hex(Web3.keccak(text="mint(address,uint256)")[:4])
            data += expected["recipient"][2:].rjust(64, "0") + format(amount, "064x")
            evidence.terms_match = all(
                evidence.decoded_intent[key] == value
                for key, value in (
                    ("to", expected["to"]),
                    ("value", "0"),
                    ("data", data),
                )
            )
        if not evidence.terms_match:
            evidence.findings.append("mint_terms_mismatch")
    evidence.findings.extend(("missing_chain_provenance", "missing_signer_authorization"))


def _decode(value, evidence):
    if value is None:
        evidence.findings.append("missing_raw_payload")
        return
    try:
        if not isinstance(value, str) or not value.startswith("0x"):
            raise ValueError
        raw = bytes.fromhex(value[2:])
        if not raw:
            raise ValueError
    except (TypeError, ValueError):
        evidence.findings.append("malformed_raw_payload")
        return
    evidence.raw_transaction = raw
    evidence.observed_hash = Web3.to_hex(Web3.keccak(raw))
    if raw[0] < 0xC0:
        evidence.findings.append("unsupported_envelope")
        return
    try:
        fields = Transaction.from_bytes(raw).as_dict()
        if fields["v"] < 37 or not 0 < fields["r"] < SECPK1_N or not 0 < fields["s"] <= SECPK1_N // 2:
            raise ValueError
        chain = (fields["v"] - 35) // 2
        sender = Account.recover_transaction(raw).lower()
        to = _address(Web3.to_hex(fields["to"])) if fields["to"] else None
        if fields["to"] and to is None:
            raise ValueError
    except Exception:
        evidence.findings.append("invalid_signature")
        return
    if any(
        not 0 <= number <= MAX_UINT256
        for number in (chain, fields["nonce"], fields["value"], fields["gas"], fields["gasPrice"])
    ):
        evidence.findings.append("unsupported_integer_range")
        return
    evidence.observed_chain_id, evidence.observed_sender, evidence.observed_nonce = (
        str(chain),
        sender,
        str(fields["nonce"]),
    )
    evidence.decoded_intent = {
        "chain_id": str(chain),
        "sender": sender,
        "nonce": str(fields["nonce"]),
        "to": to,
        "value": str(fields["value"]),
        "data": Web3.to_hex(fields["data"]),
    }
    evidence.raw_valid = True
    if chain > 2**63 - 1 or fields["nonce"] >= 2**63 - 1:
        evidence.findings.append("unsupported_integer_range")


def _analyze(snapshot):
    evidence = []
    for source in snapshot.sources:
        row = OutgoingHistoryEvidence(
            source_model=source["model"],
            source_uuid=source["uuid"],
            entry_key=source["entry_key"],
            source_fingerprint=_digest(source),
            source_snapshot=json.loads(json.dumps(source)),
            findings=[],
        )
        if source["kind"] == "share_mint":
            _mint_source(source, row)
        else:
            row.findings = ["missing_raw_payload", "missing_chain_provenance", "missing_signer_authorization"]
            if source["model"] == "blockchain.BlockchainTransaction" and source.get("related") is None:
                row.findings.append("invalid_source_link")
        row.findings = sorted(set(row.findings))
        private_entry = row.source_snapshot.get("journal_entry")
        if row.raw_transaction is not None and private_entry is not None:
            private_entry["raw_source_digest"] = _digest(private_entry.pop("raw_transaction"))
        source_terms = {
            key: value
            for key, value in source["row"].items()
            if key not in ("updated_at", "status", "tx_hash", "transaction_id", "deployment_transaction_id")
        }
        row.identity_fingerprint = _digest(
            {
                "hash": row.observed_hash,
                "operation_key": row.operation_key,
                "terms": row.expected_terms,
                "source_terms": source_terms,
                "raw_claim": _digest((source.get("journal_entry") or {}).get("raw_transaction")),
                "request_terms": [
                    {key: request[key] for key in ("uuid", "token_id", "recipient_address", "amount")}
                    for request in source.get("request_candidates", [])
                ],
            }
        )
        row.clean()
        evidence.append(row)
    return evidence


def _origin(evidence):
    return evidence.source_model, str(evidence.source_uuid), evidence.entry_key


def _reference(evidence):
    return {
        "model": evidence.source_model,
        "uuid": str(evidence.source_uuid),
        "entry_key": evidence.entry_key,
        "fingerprint": evidence.source_fingerprint,
    }


def _hold(reason, evidence=()):
    refs = sorted((_reference(row) for row in evidence), key=lambda item: json.dumps(item, sort_keys=True))
    identity = {(row.observed_chain_id, row.observed_sender) for row in evidence if row.raw_valid}
    chain, sender = (
        next(iter(identity)) if len(identity) == 1 and all(row.raw_valid for row in evidence) else (None, None)
    )
    scope = "signer" if chain and sender else "chain" if chain else "deployment"
    key = _digest({"reason": reason, "scope": scope, "chain": chain, "sender": sender, "refs": refs})
    return OutgoingCutoverHold(
        scope=scope, observed_chain_id=chain, observed_sender=sender, hold_key=key, reason=reason, evidence_refs=refs
    )


def _conflict_holds(evidence, prior):
    nonces, hashes, origins = defaultdict(list), defaultdict(list), defaultdict(list)

    def remember(row):
        if row.raw_valid:
            nonces[(row.observed_chain_id, row.observed_sender, row.observed_nonce)].append(row)
        if row.observed_hash:
            hashes[row.observed_hash].append(row)
        origins[_origin(row)].append(row)

    for row in prior:
        remember(row)
    holds = []
    for row in evidence:
        if row.raw_valid:
            for previous in nonces[(row.observed_chain_id, row.observed_sender, row.observed_nonce)]:
                if previous.observed_hash != row.observed_hash:
                    holds.append(_hold("nonce_payload_conflict", (previous, row)))
        if row.observed_hash and row.operation_key:
            for previous in hashes[row.observed_hash]:
                if previous.operation_key and previous.operation_key != row.operation_key:
                    holds.append(_hold("hash_operation_conflict", (previous, row)))
        for previous in origins[_origin(row)]:
            if previous.identity_fingerprint != row.identity_fingerprint:
                holds.append(_hold("source_identity_conflict", (previous, row)))
        remember(row)
    return holds


def _holds(evidence, prior):
    holds = [_hold(code) for code in COVERAGE_LIMITS]
    holds.extend(_hold(code, (row,)) for row in evidence for code in row.findings)
    holds.extend(_conflict_holds(evidence, prior))
    return list({hold.hold_key: hold for hold in holds}.values())


def _report(manifest, moment, evidence, holds, capture_id=None):
    return {
        "capture_id": str(capture_id) if capture_id else None,
        "manifest_digest": manifest,
        "snapshot_at": moment.isoformat(),
        "validator_version": VALIDATOR_VERSION,
        "evidence_count": len(evidence),
        "raw_valid_count": sum(row.raw_valid for row in evidence),
        "matching_mint_terms_count": sum(row.terms_match for row in evidence),
        "linked_mint_source_count": sum(row.source_link_valid for row in evidence),
        "proved_unsigned_count": sum(row.proved_unsigned for row in evidence),
        "hold_count": len(holds),
        "hold_reasons": dict(sorted(Counter(hold.reason for hold in holds).items())),
        "coverage_limits": list(COVERAGE_LIMITS),
        "cutover_authorized": False,
    }


def report_inventory(snapshot):
    require_inventory_boundary()
    try:
        evidence = _analyze(snapshot)
        holds = _holds(evidence, OutgoingHistoryEvidence.objects.all())
        return _report(_manifest(snapshot), snapshot.snapshot_at, evidence, holds)
    except Exception:
        raise OutgoingInventoryError("The outgoing history report could not be prepared.") from None


def _lock_inventory():
    connection = connections[current_alias()]
    if connection.vendor == "postgresql":
        with connections[current_alias()].cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [INVENTORY_LOCK])


def record_inventory(snapshot, capture_id):
    require_inventory_boundary()
    try:
        capture_id = UUID(str(capture_id))
        manifest = _manifest(snapshot)
        evidence = _analyze(snapshot)
        with atomic(durable=True):
            _lock_inventory()
            capture = OutgoingHistoryCapture.objects.filter(pk=capture_id).first()
            if capture is not None:
                if capture.manifest_digest != manifest:
                    raise OutgoingInventoryError("This capture ID already identifies a different source manifest.")
                return _report(
                    manifest, capture.snapshot_at, list(capture.evidence.all()), list(capture.holds.all()), capture.pk
                )
            capture = OutgoingHistoryCapture.objects.create(
                uuid=capture_id,
                validator_version=VALIDATOR_VERSION,
                scope=SCOPE,
                manifest_digest=manifest,
                snapshot_at=snapshot.snapshot_at,
            )
            holds = _holds(evidence, OutgoingHistoryEvidence.objects.all())
            for row in evidence:
                row.capture = capture
            OutgoingHistoryEvidence.objects.bulk_create(evidence)
            for hold in holds:
                hold.capture = capture
            OutgoingCutoverHold.objects.bulk_create(holds)
        return _report(manifest, capture.snapshot_at, evidence, holds, capture.pk)
    except OutgoingInventoryError:
        raise
    except Exception:
        raise OutgoingInventoryError("The outgoing history capture could not be committed.") from None
