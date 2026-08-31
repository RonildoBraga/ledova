"""
Management command to manually trigger portfolio sync for all portfolios.

Thin wrapper around PortfolioSyncService.sync_portfolio() for manual testing.
In production, this runs automatically via the procrastinate task 'sync_all_portfolios' daily at 21:00 UTC.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portfolios.models import Portfolio
from portfolios.services.sync import PortfolioSyncService
from shared.utils.logging_utils import LoggingContext


class Command(BaseCommand):
    help = "Manually trigger unified portfolio sync for all portfolios (snapshots, value calculations)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--portfolio-id",
            type=str,
            help="Sync specific portfolio by ID (optional)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to backfill (default: 30)",
        )

    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.WARNING("TRIGGERING UNIFIED PORTFOLIO SYNC"))
        self.stdout.write("=" * 60 + "\n")

        portfolio_id = options.get("portfolio_id")
        days = options.get("days", 30)

        # Calculate date range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        if portfolio_id:
            # Sync specific portfolio
            try:
                portfolio = Portfolio.objects.get(id=portfolio_id)
                self.stdout.write(
                    f"{LoggingContext.PORTFOLIOS} Syncing portfolio: {portfolio.name} " f"({start_date} to {end_date})"
                )

                result = PortfolioSyncService.sync_portfolio(
                    portfolio=portfolio,
                    start_date=start_date,
                    end_date=end_date,
                )

                if result["status"] == "success":
                    self.stdout.write("\n" + "=" * 60)
                    self.stdout.write(self.style.SUCCESS("✓ Portfolio sync completed successfully"))
                    self.stdout.write("=" * 60)
                    self.stdout.write(f"\n  Snapshots created: {result.get('snapshots_created', 0)}")
                    self.stdout.write(f"  Operations: {', '.join(result.get('operations_completed', []))}\n")
                else:
                    self.stdout.write(self.style.ERROR(f"\n✗ Portfolio sync failed: {result.get('error')}\n"))

            except Portfolio.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"\n✗ Portfolio with ID '{portfolio_id}' not found\n"))
                return

        else:
            # Sync all portfolios
            portfolios = Portfolio.objects.all()
            total_portfolios = portfolios.count()

            self.stdout.write(
                f"{LoggingContext.PORTFOLIOS} Syncing {total_portfolios} portfolio(s) "
                f"({start_date} to {end_date})...\n"
            )

            success_count = 0
            error_count = 0

            for portfolio in portfolios:
                self.stdout.write(f"  Syncing: {portfolio.name}")

                result = PortfolioSyncService.sync_portfolio(
                    portfolio=portfolio,
                    start_date=start_date,
                    end_date=end_date,
                )

                if result["status"] == "success":
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"    ✓ Snapshots created: {result.get('snapshots_created', 0)}")
                    )
                else:
                    error_count += 1
                    self.stdout.write(self.style.ERROR(f"    ✗ Failed: {result.get('error')}"))

            self.stdout.write("\n" + "=" * 60)
            self.stdout.write(
                self.style.SUCCESS(f"✓ Portfolio sync completed: {success_count} success, {error_count} errors")
            )
            self.stdout.write("=" * 60 + "\n")
