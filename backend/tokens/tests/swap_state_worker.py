import json
import logging
import os
import sys
import traceback
from unittest.mock import Mock, patch

import django


def report(stage, **values):
    print(json.dumps({"stage": stage, **values}), flush=True)


def command(expected):
    received = sys.stdin.readline().strip()
    if received != expected:
        raise AssertionError(f"Expected {expected}, received {received}")


def run(mode, row_id, detail):
    from django.conf import settings

    settings.DATABASES = {"default": json.loads(os.environ["TRADING_TEST_DATABASE"])}
    settings.RLS_AMBIENT_ALIAS = "default"
    settings.ATOMIC_SWAP_ADDRESS = "0x" + "9d" * 20
    settings.BLOCKCHAIN_OPERATOR_KEY = "0x" + "11" * 32
    settings.BLOCKCHAIN_CHAIN_ID = int(os.environ["TRADING_TEST_CHAIN_ID"])
    django.setup()
    logging.disable(logging.CRITICAL)

    from django.db import connections
    from eth_account.messages import encode_typed_data

    from shared.db import atomic
    from tokens.exceptions import SwapNotReadyException
    from tokens.models import SwapOrder, TransferOrder
    from tokens.services.token_transfer_service import TokenTransferService
    from tokens.tests.swap_state_fixtures import (
        BUYER,
        CONFIRMED,
        REVERTED,
        SELLER,
        TX_HASH,
        swap_service,
    )

    connection = connections["default"]
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '20s'")
        cursor.execute("SET lock_timeout = '15s'")
        cursor.execute("SELECT pg_backend_pid()")
        database_pid = cursor.fetchone()[0]
    row = TransferOrder.objects.get(pk=row_id) if mode == "match" else SwapOrder.objects.get(pk=row_id)
    transaction = row.transaction if mode in ("receipt", "reconcile", "receipt_locked") else None
    service = swap_service()
    report("loaded", pid=os.getpid(), database_pid=database_pid)
    command("run")

    if mode in ("execute", "execute_overlap"):
        service.validate_swap_balances = Mock()
        service._execute_swap_call = Mock()
        if mode == "execute_overlap":
            record = service._new_transaction_record

            def before_record(*args):
                report("claim_locked", in_atomic=connection.in_atomic_block)
                command("claim")
                return record(*args)

            service._new_transaction_record = before_record

        def prepare(*args, **kwargs):
            report("prepare", in_atomic=connection.in_atomic_block)
            command("prepare")
            return {}

        def sign(*args, **kwargs):
            report("sign", in_atomic=connection.in_atomic_block)
            return b"synthetic-signed-swap"

        def send(*args, **kwargs):
            report("send", in_atomic=connection.in_atomic_block)
            return TX_HASH

        service.chain_client.build_transaction.side_effect = prepare
        service.chain_client.sign_transaction.side_effect = sign
        service.chain_client.send_raw_transaction.side_effect = send
        service.chain_client.receipt_even_if_reverted.return_value = None
        try:
            result = service.execute_swap(row)
        except SwapNotReadyException:
            report("done", refused="SwapNotReadyException")
            return
    elif mode in ("signature", "signature_overlap"):
        signer = SELLER if detail == "seller" else BUYER
        signature = signer.sign_message(encode_typed_data(full_message=service.get_typed_data(row))).signature.hex()
        verify = service.verify_signature

        def verified(*args):
            result = verify(*args)
            report("verified", valid=result, in_atomic=connection.in_atomic_block)
            command("store")
            return result

        service.verify_signature = verified
        if mode == "signature_overlap":
            add_signature = SwapOrder.add_seller_signature

            def before_signature(swap, value):
                report("signature_locked", in_atomic=connection.in_atomic_block)
                command("signature")
                return add_signature(swap, value)

            with patch.object(SwapOrder, "add_seller_signature", before_signature):
                result = service.submit_signature(row, signature, signer.address).status
        else:
            result = service.submit_signature(row, signature, signer.address).status
    elif mode in ("receipt", "reconcile", "receipt_locked"):
        receipt = CONFIRMED if detail == "positive" else REVERTED

        def observation(*args):
            report("observed", in_atomic=connection.in_atomic_block)
            command("apply")
            return receipt

        if mode == "receipt_locked":
            report("applying")
            result = service._record_receipt(row, transaction, row.tx_hash, receipt)
        elif mode == "receipt":
            result = service._record_receipt(row, transaction, row.tx_hash, observation())
        else:
            service.chain_client.receipt_even_if_reverted.side_effect = observation
            contract = Mock()
            contract.events.SwapExecuted.return_value.process_receipt.return_value = [
                {"args": {"orderHash": bytes.fromhex(service.executed_order_hash(row).removeprefix("0x"))}}
            ]
            service.chain_client.load_contract.return_value = contract
            result = service.resolve_executing_swap(row)
    elif mode == "match":
        with atomic():
            match = object.__new__(TokenTransferService).find_matching_order(row)
            result = str(match[0].pk) if match else None
    else:
        raise AssertionError(mode)
    report("done", result=result)
    connections.close_all()


if __name__ == "__main__":
    try:
        with patch("tokens.events.publish_trading_event"):
            run(*sys.argv[1:])
    except BaseException:
        traceback.print_exc()
        report("error")
        sys.exit(1)
