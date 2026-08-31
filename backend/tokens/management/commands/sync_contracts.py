import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from tokens.models import Stablecoin

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync deployed contract addresses to Django database records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--stablecoin-address",
            type=str,
            help="Override stablecoin contract address (default: from STABLECOIN_CONTRACT_ADDRESS env)",
        )

    def handle(self, *args, **options):
        self.stdout.write("Syncing contract addresses to database...\n")

        stablecoin_address = options.get("stablecoin_address") or getattr(settings, "STABLECOIN_CONTRACT_ADDRESS", None)

        if not stablecoin_address:
            self.stdout.write(
                self.style.WARNING("  STABLECOIN_CONTRACT_ADDRESS not configured, skipping stablecoin sync")
            )
        else:
            self._sync_stablecoin(stablecoin_address)

        self.stdout.write(self.style.SUCCESS("\nContract sync complete!"))

    def _sync_stablecoin(self, contract_address: str):
        self.stdout.write(f"  Syncing AUDY at {contract_address}...")

        stablecoin, created = Stablecoin.objects.update_or_create(
            symbol="AUDY",
            defaults={
                "name": "AUDY",
                "contract_address": contract_address,
                "decimals": 2,
                "is_active": True,
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"    Created: {stablecoin}"))
            logger.info(f"Created Stablecoin record: {stablecoin.symbol} at {contract_address}")
        else:
            self.stdout.write(self.style.SUCCESS(f"    Updated: {stablecoin}"))
            logger.info(f"Updated Stablecoin record: {stablecoin.symbol} at {contract_address}")
