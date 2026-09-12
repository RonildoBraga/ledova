import json
import os
import signal
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import django

from blockchain.tests.outgoing_worker import await_file
from shared.tests.synthetic_store import a_private_store_that_survives_a_kill


def run(directory, phase, index):
    os.environ["DJANGO_SETTINGS_MODULE"] = "ledova_backend.settings.test"
    from django.conf import settings

    database = os.environ.get("INVENTORY_TEST_DATABASE")
    if database:
        settings.DATABASES = {"default": json.loads(database)}
    else:
        a_private_store_that_survives_a_kill(settings, directory / "inventory.sqlite3")
    django.setup()

    from django.core.management import call_command

    from blockchain.models import OutgoingCutoverHold
    from blockchain.services import outgoing_inventory as inventory
    from blockchain.tests.outgoing_inventory_fixtures import signed_source, snapshot
    from tokens.models import ShareToken
    from tokens.services import legacy_outgoing_sources as sources

    if not database and phase != "recover":
        call_command("migrate", run_syncdb=True, verbosity=0)
    source = snapshot(signed_source(index, amount=10 + index))
    capture_id = UUID(int=800 + index)
    if phase == "race":
        analyze = inventory._conflict_holds

        def analyze_after_release(evidence, prior):
            prior = list(prior)
            (directory / f"analyzing-{index}").touch()
            await_file(directory / "analyze")
            return analyze(evidence, prior)

        (directory / f"ready-{index}").touch()
        await_file(directory / "go")
        with patch.object(inventory, "_conflict_holds", analyze_after_release):
            result = inventory.record_inventory(source, capture_id)
    elif phase == "kill":

        def kill_before_holds(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGKILL)

        with patch.object(OutgoingCutoverHold.objects, "bulk_create", kill_before_holds):
            result = inventory.record_inventory(source, capture_id)
    elif phase == "snapshot":
        read = sources._rows

        def read_then_pause(model, *fields):
            rows = read(model, *fields)
            if model is ShareToken:
                (directory / "snapshot-started").touch()
                await_file(directory / "writer-finished")
            return rows

        with patch.object(sources, "_rows", read_then_pause):
            source = inventory.collect_inventory()
        result = inventory.record_inventory(source, capture_id)
    else:
        result = inventory.record_inventory(source, capture_id)
    print(json.dumps(result))


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
