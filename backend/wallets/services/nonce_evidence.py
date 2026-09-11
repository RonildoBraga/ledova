from collections.abc import Mapping

import rlp
from eth_account._utils.legacy_transactions import Transaction as LegacyTransaction
from eth_account.typed_transactions import TypedTransaction
from web3 import Web3

from integrations.blockchain.receipts import (
    nonnegative_integer,
    normalized_hash,
    transaction_hash_matches,
)
from tokens.services.signed_transactions import decode_signed_transaction
from wallets.services.receipt_readers import MAX_BLOCK_NUMBER, extract_actual_fee

MAX_NONCE = 2**64 - 1
MAX_PROBES = 66
MAX_BLOCK_TRANSACTIONS = 10000
MAX_INPUT_BYTES = 131072
MAX_ACCESS_LIST_ITEMS = 4096


def _unknown(reason, evidence):
    return {"result": "unknown", "reason": reason, "evidence": evidence}


def _block_identity(block):
    if not isinstance(block, Mapping):
        raise ValueError("Block unavailable")
    height = nonnegative_integer(block.get("number"), maximum=MAX_BLOCK_NUMBER)
    block_hash = normalized_hash(block.get("hash"))
    if height is None or block_hash is None:
        raise ValueError("Invalid block identity")
    return {"height": height, "hash": "0x" + block_hash}


def _address(value):
    if not isinstance(value, str) or not Web3.is_address(value):
        raise ValueError("Invalid address")
    return value.lower()


def _input(value):
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str) and value.startswith("0x") and len(value) <= 2 + MAX_INPUT_BYTES * 2:
        data = bytes.fromhex(value[2:])
    else:
        raise ValueError("Invalid transaction input")
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("Transaction input exceeds the observation bound")
    return data


def _quantity(value, maximum=2**256 - 1):
    result = nonnegative_integer(value, maximum=maximum)
    if result is None:
        raise ValueError("Invalid transaction quantity")
    return result


def _signature_scalar(value):
    if isinstance(value, bytes) and len(value) <= 32:
        return int.from_bytes(value, "big")
    result = nonnegative_integer(value, maximum=2**256 - 1, encoded=True)
    if result is None:
        raise ValueError("Invalid signature scalar")
    return result


def _access_list(value):
    if not isinstance(value, (list, tuple)) or len(value) > MAX_ACCESS_LIST_ITEMS:
        raise ValueError("Access list unavailable or outside the observation bound")
    result = []
    count = len(value)
    for entry in value:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("storageKeys"), (list, tuple)):
            raise ValueError("Invalid access list entry")
        count += len(entry["storageKeys"])
        if count > MAX_ACCESS_LIST_ITEMS:
            raise ValueError("Access list exceeds the observation bound")
        keys = [normalized_hash(key) for key in entry["storageKeys"]]
        if None in keys:
            raise ValueError("Invalid storage key")
        result.append(
            {
                "address": Web3.to_checksum_address(_address(entry.get("address"))),
                "storageKeys": ["0x" + key for key in keys],
            }
        )
    return result


def _signed_candidate(tx, envelope):
    fields = {
        "nonce": _quantity(tx.get("nonce"), MAX_NONCE),
        "gas": _quantity(tx.get("gas"), MAX_NONCE),
        "to": bytes.fromhex(_address(tx["to"])[2:]) if tx.get("to") is not None else b"",
        "value": _quantity(tx.get("value")),
        "data": _input(tx.get("input")),
        "v": _quantity(tx.get("v")),
        "r": _signature_scalar(tx.get("r")),
        "s": _signature_scalar(tx.get("s")),
    }
    if envelope in (0, 1):
        fields["gasPrice"] = _quantity(tx.get("gasPrice"))
    else:
        fields["maxFeePerGas"] = _quantity(tx.get("maxFeePerGas"))
        fields["maxPriorityFeePerGas"] = _quantity(tx.get("maxPriorityFeePerGas"))
    if envelope == 0:
        raw = rlp.encode(LegacyTransaction(**fields))
    else:
        fields.update(
            type=envelope, chainId=_quantity(tx.get("chainId")), accessList=_access_list(tx.get("accessList"))
        )
        raw = TypedTransaction.from_dict(fields).encode()
    if not transaction_hash_matches(Web3.keccak(raw), tx.get("hash")):
        raise ValueError("Transaction fields do not produce the observed hash")
    return decode_signed_transaction(raw)


def _intent_kind(decoded, observed):
    if observed["type"] not in (0, 1, 2):
        return "other"
    if (
        observed["to"] == decoded.to.lower()
        and observed["value"] == str(decoded.value)
        and observed["input"] == "0x" + decoded.data.hex()
    ):
        old_cap = decoded.max_fee_per_gas if decoded.envelope_type == 2 else decoded.gas_price
        old_tip = decoded.max_priority_fee_per_gas if decoded.envelope_type == 2 else decoded.gas_price
        cap, tip = observed["fee_cap"], observed["priority_cap"]
        if cap is not None and tip is not None and old_cap is not None and old_tip is not None:
            if cap >= old_cap and tip >= old_tip and (cap > old_cap or tip > old_tip):
                return "fee_bump"
        return "same_intent"
    if observed["to"] == decoded.sender.lower() and observed["value"] == "0" and observed["input"] == "0x":
        return "zero_value_self_call"
    return "other"


def _candidate(client, block, decoded, known_hash):
    identity = _block_identity(block)
    transactions = block.get("transactions")
    if not isinstance(transactions, (list, tuple)) or len(transactions) > MAX_BLOCK_TRANSACTIONS:
        raise ValueError("Full block transactions unavailable or outside the observation bound")
    matches = [
        (index, tx)
        for index, tx in enumerate(transactions)
        if isinstance(tx, Mapping)
        and isinstance(tx.get("from"), str)
        and tx["from"].lower() == decoded.sender.lower()
        and nonnegative_integer(tx.get("nonce"), maximum=MAX_NONCE) == decoded.nonce
    ]
    if len(matches) != 1:
        return None
    index, tx = matches[0]
    tx_hash = normalized_hash(tx.get("hash"))
    if (
        tx_hash is None
        or not transaction_hash_matches(tx.get("blockHash"), identity["hash"])
        or _quantity(tx.get("blockNumber"), MAX_BLOCK_NUMBER) != identity["height"]
        or _quantity(tx.get("transactionIndex"), MAX_BLOCK_TRANSACTIONS) != index
        or (tx.get("chainId") is not None and _quantity(tx["chainId"]) != decoded.chain_id)
    ):
        raise ValueError("Transaction identity disagrees with the containing block")
    tx_hash = "0x" + tx_hash
    envelope = _quantity(tx.get("type", 0), 127)
    if envelope not in (0, 1, 2):
        return None
    signed = _signed_candidate(tx, envelope)
    if (
        signed.sender.lower() != decoded.sender.lower()
        or signed.nonce != decoded.nonce
        or signed.chain_id not in (None, decoded.chain_id)
    ):
        raise ValueError("The signed candidate does not match the watched sender nonce")
    cap = signed.max_fee_per_gas if envelope == 2 else signed.gas_price
    tip = signed.max_priority_fee_per_gas if envelope == 2 else signed.gas_price
    observed = {
        "tx_hash": tx_hash,
        "sender": _address(tx["from"]),
        "nonce": decoded.nonce,
        "to": _address(tx["to"]) if tx.get("to") is not None else None,
        "value": str(_quantity(tx.get("value"))),
        "input": "0x" + _input(tx.get("input")).hex(),
        "type": envelope,
        "gas_limit": _quantity(tx.get("gas"), MAX_NONCE),
        "fee_cap": _quantity(cap) if cap is not None else None,
        "priority_cap": _quantity(tip) if tip is not None else None,
        "block": identity,
        "transaction_index": index,
    }
    receipt = client.get_transaction_receipt(tx_hash)
    if (
        not isinstance(receipt, Mapping)
        or not transaction_hash_matches(receipt.get("transactionHash"), tx_hash)
        or not transaction_hash_matches(receipt.get("blockHash"), identity["hash"])
        or nonnegative_integer(receipt.get("blockNumber"), maximum=MAX_BLOCK_NUMBER) != identity["height"]
        or nonnegative_integer(receipt.get("transactionIndex"), maximum=MAX_BLOCK_TRANSACTIONS) != index
        or nonnegative_integer(receipt.get("status"), maximum=1) is None
        or _address(receipt.get("from")) != observed["sender"]
        or (_address(receipt["to"]) if receipt.get("to") is not None else None) != observed["to"]
    ):
        raise ValueError("Candidate receipt unavailable or inconsistent")
    fee = extract_actual_fee(receipt, "ethereum")
    if fee is not None:
        gas_used = _quantity(receipt.get("gasUsed"))
        price = _quantity(receipt.get("effectiveGasPrice"))
        if gas_used > observed["gas_limit"] or (
            envelope in (0, 1, 2)
            and observed["fee_cap"] is not None
            and (
                price > observed["fee_cap"]
                or (envelope in (0, 1) and price != observed["fee_cap"])
                or (envelope == 2 and price < min(observed["fee_cap"], observed["priority_cap"]))
            )
        ):
            raise ValueError("Receipt fee disagrees with the transaction limits")
    observed["succeeded"] = receipt["status"] == 1
    observed["actual_fee"] = str(fee) if fee is not None else None
    observed["intent_kind"] = "original" if tx_hash == known_hash else _intent_kind(decoded, observed)
    return observed


def _locate(client, decoded, known_hash, head, evidence, admission):
    cache = {}
    probes = evidence["nonce_probes"] = []

    def nonce_at(height):
        if height not in cache:
            if len(cache) >= MAX_PROBES:
                raise ValueError("Nonce search exceeded its observation bound")
            value = _quantity(client.w3.eth.get_transaction_count(decoded.sender, height), MAX_NONCE)
            if any((h < height and n > value) or (h > height and n < value) for h, n in cache.items()):
                raise ValueError("Nonce observations are not monotonic")
            cache[height] = value
            probes.append({"height": height, "nonce": value})
        return cache[height]

    if nonce_at(head["height"]) <= decoded.nonce:
        return {"result": "unconsumed", "reason": "nonce_not_mined"}
    lower, upper = 0, head["height"]
    if admission is not None:
        anchor = _block_identity({"number": admission.get("block_number"), "hash": admission.get("block_hash")})
        if _quantity(admission.get("chain_id")) != decoded.chain_id:
            raise ValueError("Admission network does not match the signed transaction")
        if _quantity(admission.get("nonce"), MAX_NONCE) > decoded.nonce:
            raise ValueError("Admission nonce conflicts with the signed transaction")
        evidence["admission_anchor"] = anchor
        if anchor["height"] <= upper and _block_identity(client.w3.eth.get_block(anchor["height"])) == anchor:
            lower = anchor["height"]
            if nonce_at(lower) != admission["nonce"]:
                raise ValueError("Canonical admission nonce changed")
        else:
            evidence["admission_orphaned"] = True
    if nonce_at(lower) > decoded.nonce:
        return {"result": "unknown", "reason": "nonce_predates_available_chain"}
    while upper - lower > 1:
        middle = (lower + upper) // 2
        if nonce_at(middle) <= decoded.nonce:
            lower = middle
        else:
            upper = middle
    block = client.w3.eth.get_block(upper, full_transactions=True)
    identity = _block_identity(block)
    if identity["height"] != upper:
        raise ValueError("Nonce search returned a different block height")
    evidence["consuming_block"] = identity
    candidate = _candidate(client, block, decoded, known_hash)
    if _block_identity(client.w3.eth.get_block(upper)) != identity:
        raise ValueError("The consuming block changed during the observation")
    if candidate is None:
        return {"result": "unknown", "reason": "consumed_nonce_not_attributed_to_a_sender_transaction"}
    return {"result": "candidate", "reason": "", "candidate": candidate}


def collect_nonce_evidence(client, signed_transaction, *, admission=None):
    evidence = {"complete": False}
    try:
        raw = bytes(signed_transaction)
        decoded = decode_signed_transaction(raw)
        _quantity(decoded.nonce, MAX_NONCE)
        if decoded.chain_id is None or decoded.to is None:
            return _unknown("intent_unavailable", evidence)
        known_hash = Web3.keccak(raw).to_0x_hex()
    except (ValueError, TypeError):
        return _unknown("intent_unavailable", evidence)
    evidence["target"] = {
        "chain_id": decoded.chain_id,
        "sender": decoded.sender.lower(),
        "nonce": decoded.nonce,
        "tx_hash": known_hash,
    }
    try:
        if _quantity(client.assert_expected_chain()) != decoded.chain_id:
            return _unknown("network_mismatch", evidence)
        head = _block_identity(client.w3.eth.get_block("latest"))
        evidence["head"] = head
        result = _locate(client, decoded, known_hash, head, evidence, admission)
        evidence["last_head"] = _block_identity(client.w3.eth.get_block("latest"))
        if _quantity(client.assert_expected_chain()) != decoded.chain_id:
            return _unknown("network_changed", evidence)
        if evidence["last_head"] != head:
            return _unknown("head_changed", evidence)
        evidence["complete"] = True
        return {**result, "evidence": evidence}
    except Exception:
        return _unknown("provider_evidence_unavailable", evidence)
