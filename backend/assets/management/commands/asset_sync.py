from django.core.management.base import BaseCommand

from assets.services import AssetSyncService


class Command(BaseCommand):
    help = "Sync all assets: creates assets, syncs prices, and backfills historical data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--today-only",
            action="store_true",
            help="Only sync current prices (skip historical backfill)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Number of days to backfill (default: 365, ignored with --today-only)",
        )

    def handle(self, *args, **options):
        today_only = options["today_only"]
        days = options["days"]

        if today_only:
            self.stdout.write("\nStarting asset sync (today only)...\n")
        else:
            self.stdout.write(f"\nStarting full asset sync (backfill {days} days)...\n")

        result = AssetSyncService.sync_assets(
            backfill_days=days,
            today_only=today_only,
        )

        if result["status"] == "success":
            self.stdout.write(self.style.SUCCESS("\n✓ Asset sync completed successfully"))
            self.stdout.write(f"  Assets created: {result['assets_created']}")
            self.stdout.write(f"  Assets updated: {result['assets_updated']}")
            self.stdout.write(f"  Prices updated: {result['prices_updated']}")
            self.stdout.write(f"  Current snapshots: {result['snapshots_created']}")
            self.stdout.write(f"  Historical snapshots: {result['historical_snapshots']}")
            self.stdout.write(f"  Operations: {', '.join(result['operations_completed'])}\n")
        else:
            self.stdout.write(self.style.ERROR(f"\n✗ Asset sync failed: {result.get('error')}\n"))
