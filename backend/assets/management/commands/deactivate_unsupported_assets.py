from django.core.management.base import BaseCommand

from assets.models import Asset
from shared.constants import SUPPORTED_CHAINS


class Command(BaseCommand):
    help = "Deactivate assets that are not on supported chains"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deactivated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        supported_assets = Asset.objects.filter(chain_deployments__chain__in=SUPPORTED_CHAINS).distinct()
        unsupported_assets = Asset.objects.exclude(uuid__in=supported_assets.values("uuid"))

        if not unsupported_assets.exists():
            self.stdout.write(
                self.style.SUCCESS("\nNo unsupported assets found. All assets are on supported chains.\n")
            )
            return

        self.stdout.write(f"\nFound {unsupported_assets.count()} assets on unsupported chains:\n")

        for asset in unsupported_assets:
            status = "active" if asset.is_active else "inactive"
            chains = list(asset.chain_deployments.values_list("chain", flat=True))
            self.stdout.write(f"  - {asset.symbol} ({asset.name}) - chains: {chains or 'none'} - currently: {status}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] No changes made. Run without --dry-run to deactivate.\n"))
            return

        updated_count = unsupported_assets.filter(is_active=True).update(is_active=False)

        self.stdout.write(self.style.SUCCESS(f"\n✓ Deactivated {updated_count} unsupported assets"))
        self.stdout.write(f"  Supported chains: {', '.join(sorted(SUPPORTED_CHAINS))}\n")
