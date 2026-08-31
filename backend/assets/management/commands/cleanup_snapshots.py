"""
Management command to clean up duplicate asset snapshots.

Keeps only one snapshot per asset per day (the most recent one for each day),
and normalizes timestamps to midnight UTC.
"""

from datetime import datetime, time
from datetime import timezone as dt_timezone

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import TruncDate

from assets.models import Asset, AssetSnapshot


class Command(BaseCommand):
    help = "Clean up duplicate asset snapshots, keeping one per asset per day"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write("\n=== DRY RUN MODE - No changes will be made ===\n")

        # Get counts before cleanup
        total_before = AssetSnapshot.objects.count()
        self.stdout.write(f"Total snapshots before cleanup: {total_before}")

        # Find assets with duplicate snapshots per day
        assets_with_duplicates = (
            AssetSnapshot.objects.annotate(date=TruncDate("source_timestamp"))
            .values("asset", "date")
            .annotate(count=Count("uuid"))
            .filter(count__gt=1)
        )

        if not assets_with_duplicates.exists():
            self.stdout.write(self.style.SUCCESS("\nNo duplicate snapshots found. Database is clean."))
            return

        # Count duplicates
        duplicate_days = assets_with_duplicates.count()
        self.stdout.write(f"Found {duplicate_days} asset-day combinations with duplicates\n")

        total_deleted = 0
        total_normalized = 0

        # Process each asset
        for asset in Asset.objects.all():
            asset_snapshots = list(AssetSnapshot.objects.filter(asset=asset).order_by("source_timestamp"))

            if not asset_snapshots:
                continue

            # Group snapshots by date
            snapshots_by_date = {}
            for snapshot in asset_snapshots:
                date_key = snapshot.source_timestamp.date()
                if date_key not in snapshots_by_date:
                    snapshots_by_date[date_key] = []
                snapshots_by_date[date_key].append(snapshot)

            asset_deleted = 0

            for date_key, snapshots in snapshots_by_date.items():
                # Calculate midnight for this date
                midnight = datetime.combine(date_key, time.min, tzinfo=dt_timezone.utc)

                if len(snapshots) > 1:
                    # Multiple snapshots for this day - need to consolidate

                    # Check if any snapshot is already at midnight
                    midnight_snapshot = None
                    other_snapshots = []
                    for s in snapshots:
                        if s.source_timestamp == midnight:
                            midnight_snapshot = s
                        else:
                            other_snapshots.append(s)

                    if midnight_snapshot:
                        # Keep the midnight one, delete all others
                        to_delete = other_snapshots
                        # Update midnight snapshot with the latest price
                        latest = max(snapshots, key=lambda s: s.source_timestamp)
                        if latest.uuid != midnight_snapshot.uuid:
                            if not dry_run:
                                midnight_snapshot.price = latest.price
                                midnight_snapshot.market_data = latest.market_data
                                midnight_snapshot.save(update_fields=["price", "market_data", "updated_at"])
                    else:
                        # No midnight snapshot exists - keep the latest, update it to midnight
                        snapshots.sort(key=lambda s: s.source_timestamp)
                        to_keep = snapshots[-1]
                        to_delete = snapshots[:-1]

                        if not dry_run:
                            # First delete duplicates to free up the constraint
                            for snapshot in to_delete:
                                snapshot.delete()

                            # Then update the kept one to midnight
                            to_keep.source_timestamp = midnight
                            to_keep.save(update_fields=["source_timestamp", "updated_at"])

                        asset_deleted += len(to_delete)
                        continue  # Skip the deletion below since we already did it

                    if not dry_run:
                        for snapshot in to_delete:
                            snapshot.delete()

                    asset_deleted += len(to_delete)

                else:
                    # Single snapshot - normalize to midnight if needed
                    snapshot = snapshots[0]
                    if snapshot.source_timestamp != midnight:
                        if not dry_run:
                            snapshot.source_timestamp = midnight
                            snapshot.save(update_fields=["source_timestamp", "updated_at"])
                        total_normalized += 1

            if asset_deleted > 0:
                total_deleted += asset_deleted
                action = "Would delete" if dry_run else "Deleted"
                self.stdout.write(f"  {asset.symbol}: {action} {asset_deleted} duplicate snapshots")

        # Summary
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Would delete {total_deleted} duplicate snapshots"))
            self.stdout.write(f"Would normalize {total_normalized} timestamps to midnight UTC")
        else:
            self.stdout.write(self.style.SUCCESS(f"Deleted {total_deleted} duplicate snapshots"))
            self.stdout.write(f"Normalized {total_normalized} timestamps to midnight UTC")

            total_after = AssetSnapshot.objects.count()
            self.stdout.write(f"\nTotal snapshots after cleanup: {total_after}")
            self.stdout.write(f"Space saved: {total_before - total_after} rows")
