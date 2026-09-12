import json
import os
import signal
import sqlite3
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import django

from shared.tests.synthetic_store import a_private_store_that_survives_a_kill


def run_worker(directory, phase):
    os.environ["DJANGO_SETTINGS_MODULE"] = "ledova_backend.settings.test"
    from django.conf import settings

    a_private_store_that_survives_a_kill(settings, directory / "mint.sqlite3")
    settings.BLOCKCHAIN_CHAIN_ID = 31337
    settings.BLOCKCHAIN_OPERATOR_KEY = "0x" + "11" * 32
    django.setup()

    from django.core.management import call_command
    from eth_account import Account
    from web3 import Web3

    from integrations.base_chain.client import BaseChainClient
    from shared.tests.tenants import make_tenant
    from tokens.models import RequestStatus, ShareIssuanceRequest
    from tokens.services import ShareTokenService

    ledger_path = directory / "node.json"
    if phase != "recover":
        call_command("migrate", run_syncdb=True, verbosity=0)
        tenant = make_tenant("mint-journal")
        request = ShareIssuanceRequest.objects.create(
            token=tenant.deployed_token,
            recipient_address="0x" + "aa" * 20,
            amount=10,
            reason="Synthetic crash recovery",
            status=RequestStatus.APPROVED,
        )
    else:
        request = ShareIssuanceRequest.objects.get(reason="Synthetic crash recovery")

    client = object.__new__(BaseChainClient)
    client._web3 = Web3()
    client.assert_expected_chain = Mock(return_value=31337)
    client.load_contract = Mock()
    signer = Account.from_key(settings.BLOCKCHAIN_OPERATOR_KEY)
    transaction = {
        "from": signer.address,
        "to": Web3.to_checksum_address(request.token.contract_address),
        "chainId": 31337,
        "nonce": 7,
        "value": 0,
        "gasPrice": 10**9,
        "gas": 100000,
        "data": "0x40c10f19" + "0" * 24 + request.recipient_address[2:] + f"{request.amount:064x}",
    }
    client.build_transaction = Mock(return_value=transaction)
    if phase == "recover":
        client.build_transaction.side_effect = AssertionError("Recovery must not sign a new mint")
    receipt = {"status": 1, "blockNumber": 9, "gasUsed": 60000}

    def broadcast(raw):
        tx_hash = Web3.to_hex(Web3.keccak(raw))
        if phase == "before_send":
            os.kill(os.getpid(), signal.SIGKILL)
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"hashes": [], "broadcasts": []}
        ledger["broadcasts"].append(Web3.to_hex(raw))
        if tx_hash not in ledger["hashes"]:
            ledger["hashes"].append(tx_hash)
        ledger_path.write_text(json.dumps(ledger))
        if phase == "after_send":
            os.kill(os.getpid(), signal.SIGKILL)
        with sqlite3.connect(directory / "mint.sqlite3") as independent:
            saved_hash, saved_journal = independent.execute(
                "SELECT tx_hash, mint_journal FROM tokens_shareissuance"
            ).fetchone()
        assert saved_hash == tx_hash
        assert json.loads(saved_journal)[-1]["raw_transaction"] == Web3.to_hex(raw)
        return tx_hash

    def read_receipt(tx_hash):
        if not ledger_path.exists():
            return None
        ledger = json.loads(ledger_path.read_text())
        if phase == "recover" and len(ledger["broadcasts"]) == 1:
            return None
        return receipt if tx_hash in ledger["hashes"] else None

    client.send_raw_transaction = broadcast
    client.get_transaction_receipt = read_receipt
    client.wait_for_receipt = Mock(return_value=receipt)
    with patch("tokens.services.share_token_service.get_base_chain_client", return_value=client):
        service = ShareTokenService()
        service.read_paused = Mock(return_value=False)
        service.is_recipient_whitelisted = Mock(return_value=True)
        service.share_supply = Mock(return_value=(1000, 0))
        service._seed_recipient_holding = Mock()
        if phase == "recover":
            service.resolve_executing_issuance(request)
            request.refresh_from_db()
            if request.status != RequestStatus.EXECUTED:
                service.resolve_executing_issuance(request)
            request.refresh_from_db()
            assert request.status == RequestStatus.EXECUTED
        else:
            service.execute_request(request)


if __name__ == "__main__":
    run_worker(Path(sys.argv[1]), sys.argv[2])
