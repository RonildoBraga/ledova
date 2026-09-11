from collections.abc import Mapping

from integrations.blockchain.receipts import (
    nonnegative_integer,
    normalized_hash,
    transaction_hash_matches,
)
from shared.constants import BLOCKCHAIN_BITCOIN
from wallets.models import ChainObservationFinality, ChainObservationResult
from wallets.services.bitcoin_intent import GENESIS_HASHES, verified_bitcoin_network
from wallets.services.receipt_readers import (
    MAX_BLOCK_NUMBER,
    extract_actual_fee,
    get_receipt_reader,
)


def _block_identity(chain, value):
    if not isinstance(value, Mapping):
        return None
    block_hash = normalized_hash(value.get("hash"))
    height = nonnegative_integer(value.get("height"), maximum=MAX_BLOCK_NUMBER)
    if block_hash is None or height is None:
        return None
    return {"hash": block_hash if chain == BLOCKCHAIN_BITCOIN else "0x" + block_hash, "height": height}


def _block(client, chain, identifier):
    if chain == BLOCKCHAIN_BITCOIN:
        block_hash = client.get_best_block_hash() if identifier == "latest" else client.get_block_hash(identifier)
        header = client.get_block_header(block_hash)
        block = _block_identity(chain, header)
        if block is None or not transaction_hash_matches(block["hash"], block_hash):
            return None
    else:
        header = client.w3.eth.get_block(identifier)
        if not isinstance(header, Mapping):
            return None
        block = _block_identity(
            chain,
            {
                "hash": header.get("hash"),
                "height": nonnegative_integer(header.get("number"), maximum=MAX_BLOCK_NUMBER, encoded=True),
            },
        )
    if isinstance(identifier, int) and (block is None or block["height"] != identifier):
        return None
    return block


def _network_matches(client, chain, network):
    if chain == BLOCKCHAIN_BITCOIN:
        name = verified_bitcoin_network(client)
        return network == "bitcoin:" + GENESIS_HASHES[name]
    chain_id = client.assert_expected_chain()
    return not isinstance(chain_id, bool) and isinstance(chain_id, int) and network == f"evm:{chain_id}"


def _receipt(client, chain, tx_hash):
    receipt = client.get_transaction_receipt(tx_hash)
    key = "tx_hash" if chain == BLOCKCHAIN_BITCOIN else "transactionHash"
    if not isinstance(receipt, Mapping) or not transaction_hash_matches(receipt.get(key), tx_hash):
        return None
    reader = get_receipt_reader(chain)
    height = reader.block_number(receipt)
    timestamp = reader.block_timestamp(client, receipt, height)
    fee = extract_actual_fee(receipt, chain)
    return {
        "hash": reader.block_hash(receipt),
        "height": height,
        "succeeded": reader.succeeded(receipt),
        "timestamp": timestamp.isoformat() if timestamp is not None else None,
        "actual_fee": str(fee) if fee is not None else None,
    }


def _canonical_context(client, chain, block, head):
    if block is None or head is None or block["height"] > head["height"]:
        return None
    return _block(client, chain, block["height"])


def _unknown(reason, evidence=None):
    return {
        "result": ChainObservationResult.UNKNOWN,
        "finality": ChainObservationFinality.UNKNOWN,
        "reason": reason,
        "evidence": evidence or {},
    }


def _finality(receipt_block, head, finalized, canonical_finalized, policy, chain):
    mode = policy.get("mode") if isinstance(policy, Mapping) else None
    if mode == "depth":
        depth = nonnegative_integer(policy.get("depth"), maximum=MAX_BLOCK_NUMBER)
        if depth is None or depth == 0:
            return ChainObservationFinality.UNKNOWN, "policy_invalid"
        satisfied = head["height"] - receipt_block["height"] + 1 >= depth
    elif mode == "finalized" and chain != BLOCKCHAIN_BITCOIN:
        if finalized is None or canonical_finalized != finalized or finalized["height"] > head["height"]:
            return ChainObservationFinality.UNKNOWN, "finality_unavailable"
        satisfied = receipt_block["height"] <= finalized["height"]
    else:
        return ChainObservationFinality.UNKNOWN, "policy_unconfigured" if mode == "unconfigured" else "policy_invalid"
    return (
        (ChainObservationFinality.SATISFIED, "")
        if satisfied
        else (ChainObservationFinality.WAITING, "finality_waiting")
    )


def collect_chain_evidence(client, *, chain, network, tx_hash, previous_block, policy):
    evidence = {"network": network, "tx_hash": tx_hash, "complete": False}
    try:
        if not _network_matches(client, chain, network):
            return _unknown("network_mismatch", evidence)
        head = _block(client, chain, "latest")
        evidence["head"] = head
        if head is None:
            return _unknown("head_unavailable", evidence)
        receipt = _receipt(client, chain, tx_hash)
        evidence["receipt"] = receipt
        receipt_block = _block_identity(chain, receipt)
        previous = _block_identity(chain, previous_block)
        evidence["previous_block"] = previous
        canonical_receipt = _canonical_context(client, chain, receipt_block, head)
        evidence["canonical_receipt"] = canonical_receipt
        canonical_previous = _canonical_context(client, chain, previous, head)
        evidence["canonical_previous"] = canonical_previous
        finalized = None
        canonical_finalized = None
        if isinstance(policy, Mapping) and policy.get("mode") == "finalized" and chain != BLOCKCHAIN_BITCOIN:
            try:
                finalized = _block(client, chain, "finalized")
                canonical_finalized = _canonical_context(client, chain, finalized, head)
            except Exception:
                evidence["finality_read_failed"] = True
        last_head = _block(client, chain, "latest")
        evidence.update(
            {
                "head": head,
                "last_head": last_head,
                "receipt": receipt,
                "canonical_receipt": canonical_receipt,
                "previous_block": previous,
                "canonical_previous": canonical_previous,
                "finalized": finalized,
                "canonical_finalized": canonical_finalized,
            }
        )
        if not _network_matches(client, chain, network):
            return _unknown("network_changed", evidence)
        if last_head != head:
            return _unknown("head_changed", evidence)
        evidence["complete"] = True
        previous_orphaned = previous is not None and canonical_previous is not None and previous != canonical_previous
        evidence["previous_orphaned"] = previous_orphaned
        if previous is not None and receipt_block is not None and previous != receipt_block and not previous_orphaned:
            reason = (
                "previous_inclusion_still_canonical"
                if canonical_previous == previous
                else "previous_canonicality_unavailable"
            )
            return _unknown(reason, evidence)
        if receipt_block is None or receipt["succeeded"] is None or canonical_receipt is None:
            if previous_orphaned:
                return {
                    "result": ChainObservationResult.ORPHANED,
                    "finality": ChainObservationFinality.UNKNOWN,
                    "reason": "previous_block_replaced",
                    "evidence": evidence,
                }
            return _unknown("receipt_unavailable", evidence)
        if receipt_block != canonical_receipt:
            return {
                "result": ChainObservationResult.ORPHANED,
                "finality": ChainObservationFinality.UNKNOWN,
                "reason": "receipt_block_replaced",
                "evidence": evidence,
            }
        evidence["depth"] = head["height"] - receipt_block["height"] + 1
        finality, reason = _finality(receipt_block, head, finalized, canonical_finalized, policy, chain)
        return {
            "result": ChainObservationResult.INCLUDED,
            "finality": finality,
            "reason": reason,
            "evidence": evidence,
        }
    except Exception:
        return _unknown("provider_unavailable", evidence)
