import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from blockchain.services.outgoing_inventory import (
    OutgoingInventoryError,
    collect_inventory,
    record_inventory,
    report_inventory,
    require_inventory_boundary,
)
from shared.db import use_operator


class Command(BaseCommand):
    help = "Report or stage private legacy outgoing observations without signing, sending or authorizing cutover."

    def add_arguments(self, parser):
        parser.add_argument("--record", action="store_true")
        parser.add_argument("--capture-id", type=UUID)

    def handle(self, *args, **options):
        if options["record"] != bool(options["capture_id"]):
            raise CommandError("Recording requires both --record and --capture-id.")
        try:
            require_inventory_boundary()
            with use_operator():
                snapshot = collect_inventory()
                result = (
                    record_inventory(snapshot, options["capture_id"])
                    if options["record"]
                    else report_inventory(snapshot)
                )
        except OutgoingInventoryError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(result, sort_keys=True))
