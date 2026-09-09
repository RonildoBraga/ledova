import hashlib
import json
from uuid import UUID

from django.utils import timezone
from eth_account import Account
from web3 import Web3

from blockchain.services.outgoing_inventory import InventorySnapshot
from blockchain.tests.outgoing_fixtures import CHAIN_ID, KEY, SENDER

RECIPIENT = "0x" + "bb" * 20
CONTRACT = "0x" + "cc" * 20
TOKEN_ID = str(UUID(int=300))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def signed_source(index=0, *, amount=10, transaction_changes=None):
    transaction = {
        "chainId": CHAIN_ID,
        "nonce": 7,
        "to": Web3.to_checksum_address(CONTRACT),
        "value": 0,
        "gas": 100000,
        "gasPrice": 10**9,
        "data": "0x40c10f19" + RECIPIENT[2:].rjust(64, "0") + f"{amount:064x}",
    }
    transaction.update(transaction_changes or {})
    signed = Account.sign_transaction(transaction, KEY)
    tx_hash = Web3.to_hex(signed.hash)
    entry = {
        "id": str(UUID(int=400 + index)),
        "tx_hash": tx_hash,
        "raw_transaction": Web3.to_hex(signed.raw_transaction),
        "signed_at": "2026-09-01T00:00:00+00:00",
    }
    issuance_id, request_id = str(UUID(int=1 + index)), str(UUID(int=100 + index))
    return {
        "model": "tokens.ShareIssuance",
        "uuid": issuance_id,
        "entry_key": "journal:0",
        "kind": "share_mint",
        "row": {
            "uuid": issuance_id,
            "updated_at": "2026-09-01T00:00:00+00:00",
            "token_id": TOKEN_ID,
            "recipient_address": RECIPIENT,
            "amount": str(amount),
            "status": "failed",
            "tx_hash": tx_hash,
            "idempotency_key": f"issuance-request:{request_id}",
            "transaction_id": None,
        },
        "token": {"uuid": TOKEN_ID, "contract_address": CONTRACT, "decimals": 0, "chain": "base"},
        "request_candidates": [
            {
                "uuid": request_id,
                "token_id": TOKEN_ID,
                "recipient_address": RECIPIENT,
                "amount": amount,
                "status": "failed",
                "executed_issuance_id": None,
            }
        ],
        "capital_links": [],
        "journal_shape": "entries",
        "journal_digest": digest([entry]),
        "is_current_entry": True,
        "entry_keys": sorted(entry),
        "journal_entry": entry,
        "entry_digest": digest(entry),
        "attempt_id_unique": True,
    }


def snapshot(*sources, moment=None):
    return InventorySnapshot(moment or timezone.now(), tuple(sources or (signed_source(),)))


def observed_identity():
    return str(CHAIN_ID), SENDER.lower(), "7"
