from django.core.management.base import BaseCommand

from shared.services.orphaned_files import GRACE, sweep_orphaned_files


class Command(BaseCommand):
    help = (
        "Delete private uploads that no row references and that have not changed for "
        f"{int(GRACE.total_seconds() // 3600)} hours."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = sweep_orphaned_files(dry_run=options["dry_run"])

        if options["verbosity"] >= 1:
            for name in result["names"]:
                self.stdout.write(f"orphan {name}")
            verb = "would delete" if options["dry_run"] else "deleted"
            self.stdout.write(f"{result['found']} orphaned, {verb} {result['deleted']}, failed {result['failed']}")

        return None
