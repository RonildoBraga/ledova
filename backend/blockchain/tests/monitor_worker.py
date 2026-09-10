import json
import logging
import os
import sys
from unittest.mock import patch

import django


def report(stage, **values):
    print(json.dumps({"stage": stage, **values}, default=str), flush=True)


def command(expected):
    received = sys.stdin.readline().strip()
    if received != expected:
        raise AssertionError(f"Expected {expected}, received {received}")


def run(receipt_status, mode):
    from django.conf import settings

    database = json.loads(os.environ["MONITOR_TEST_DATABASE"])
    settings.DATABASES = {"default": database.copy(), "operator": database.copy()}
    settings.RLS_AMBIENT_ALIAS = "operator"
    django.setup()
    logging.disable(logging.CRITICAL)

    from django.db import connections

    from blockchain.models import BlockchainTransaction
    from blockchain.tests.monitor_fixtures import RECEIPT, stored, sweep
    from shared.db import current_alias

    connection = connections[current_alias()]
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '20s'")
        cursor.execute("SET lock_timeout = '15s'")
        cursor.execute("SELECT pg_backend_pid()")
        database_pid = cursor.fetchone()[0]
    report("loaded", pid=os.getpid(), database_pid=database_pid, alias=current_alias())
    command("run")

    def observation(requested_hash):
        report("observed", requested_hash=requested_hash, in_atomic=connection.in_atomic_block)
        command("apply")
        return {**RECEIPT, "transactionHash": requested_hash, "status": receipt_status}

    method_name = "mark_confirmed" if receipt_status else "mark_reverted"
    method = getattr(BlockchainTransaction, method_name)

    def write(current, *args, **kwargs):
        report("locked", in_atomic=connection.in_atomic_block, status=current.status)
        command("commit")
        return method(current, *args, **kwargs)

    if mode == "overlap":
        with patch.object(BlockchainTransaction, method_name, write):
            result = sweep(observation)
    else:
        result = sweep(observation)
    current = BlockchainTransaction.objects.get()
    report("done", result=result, stored=stored(current))
    connections.close_all()


if __name__ == "__main__":
    run(int(sys.argv[1]), sys.argv[2])
