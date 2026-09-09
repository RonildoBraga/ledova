import json
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import patch

import django


def await_file(path):
    until = time.monotonic() + 20
    while not path.exists():
        if time.monotonic() > until:
            raise RuntimeError("The synthetic process gate was never released")
        time.sleep(0.01)


def run(directory, phase, index):
    os.environ["DJANGO_SETTINGS_MODULE"] = "ledova_backend.settings.test"
    from django.conf import settings

    database = os.environ.get("OUTGOING_TEST_DATABASE")
    if database:
        settings.DATABASES = {"default": json.loads(database)}
    else:
        settings.DATABASES["default"]["NAME"] = str(directory / "outgoing.sqlite3")
    django.setup()

    from django.core.management import call_command
    from eth_account.signers.local import LocalAccount
    from web3 import Web3

    from blockchain.models import OutgoingOperation, OutgoingStatus
    from blockchain.services.outgoing import (
        broadcast_operation,
        prepare_operation,
        record_receipt,
        sign_operation,
    )
    from blockchain.tests.outgoing_fixtures import (
        KEY,
        chain_client,
        claim_operation,
        receipt,
    )

    if not database and phase != "recover":
        call_command("migrate", run_syncdb=True, verbosity=0)
    key = "synthetic:process" if phase not in ("race", "sign", "blocked_send") else f"synthetic:race:{index}"
    claim = claim_operation(key)
    client = chain_client()
    operation = OutgoingOperation.objects.get(pk=claim.operation_id)
    if operation.status == OutgoingStatus.PREPARING:
        prepared = prepare_operation(claim, client)
        if phase == "race":
            (directory / f"ready-{os.getpid()}").touch()
            await_file(directory / "go")
        save = OutgoingOperation.save

        def save_then_kill(row, *args, **kwargs):
            save(row, *args, **kwargs)
            if row.status == OutgoingStatus.SIGNED:
                os.kill(os.getpid(), signal.SIGKILL)

        local_sign = LocalAccount.sign_transaction

        def sign_after_release(account, *args, **kwargs):
            (directory / f"signing-{os.getpid()}").touch()
            await_file(directory / "sign")
            return local_sign(account, *args, **kwargs)

        if phase == "before_commit":
            with patch.object(OutgoingOperation, "save", save_then_kill):
                attempt = sign_operation(claim, prepared, KEY)
        elif phase == "race":
            with patch.object(LocalAccount, "sign_transaction", sign_after_release):
                attempt = sign_operation(claim, prepared, KEY)
        else:
            attempt = sign_operation(claim, prepared, KEY)
    else:
        attempt = operation.current_attempt

    if phase in ("race", "sign"):
        print(json.dumps({"hash": attempt.tx_hash, "nonce": attempt.nonce}))
        return

    ledger_path = directory / "node.json"

    def broadcast(raw):
        if phase == "before_send":
            os.kill(os.getpid(), signal.SIGKILL)
        if phase == "blocked_send":
            (directory / "sending").touch()
            await_file(directory / "release")
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"hashes": [], "broadcasts": []}
        tx_hash = Web3.to_hex(Web3.keccak(raw))
        ledger["broadcasts"].append(Web3.to_hex(raw))
        if tx_hash not in ledger["hashes"]:
            ledger["hashes"].append(tx_hash)
        ledger_path.write_text(json.dumps(ledger))
        if phase == "after_send":
            os.kill(os.getpid(), signal.SIGKILL)
        return tx_hash

    client.send_raw_transaction = broadcast
    result = broadcast_operation(claim, client)
    assert result.tx_hash == attempt.tx_hash and result.acknowledged
    record_receipt(claim, attempt.tx_hash, receipt(attempt))
    print(json.dumps({"hash": attempt.tx_hash, "nonce": attempt.nonce}))


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "0")
