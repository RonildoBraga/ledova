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
        parser.add_argument(
            "--seed-only",
            action="store_true",
            help="Only upsert the supported assets and their chain deployments; no price fetch, no network",
        )

    def handle(self, *args, **options):
        today_only = options["today_only"]
        days = options["days"]

        if options["seed_only"]:
            AssetSyncService.ensure_supported_assets()
            self.stdout.write(self.style.SUCCESS("✓ Supported assets seeded"))
            return

        if today_only:
            self.stdout.write("\nStarting asset sync (today only)...\n")
        else:
            self.stdout.write(f"\nStarting full asset sync (backfill {days} days)...\n")

        AssetSyncService.ensure_supported_assets()
        result = AssetSyncService.sync_assets(backfill_days=days, today_only=today_only)

        if result["status"] == "success":
            self.stdout.write(self.style.SUCCESS("\n✓ Asset sync completed successfully"))
            self.stdout.write(f"  Prices updated: {result['prices_updated']}")
            self.stdout.write(f"  Historical snapshots: {result['historical_snapshots']}\n")
        else:
            self.stdout.write(self.style.ERROR(f"\n✗ Asset sync failed: {result.get('error')}\n"))
