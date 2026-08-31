"""
Management command to reconcile country names based on their codes.
"""

from django.core.management.base import BaseCommand

from shared.services.country_service import CountryService


class Command(BaseCommand):
    """
    Reconciles country names in the database based on their country codes.

    This command will iterate through all countries in the database and update
    their names based on their country codes using ISO 3166-1 mappings.

    Usage:
        python manage.py reconcile_countries
        python manage.py reconcile_countries --country-code US
        python manage.py reconcile_countries --dry-run
    """

    help = "Reconcile country names based on their country codes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--country-code", type=str, help="Reconcile a specific country by its code (e.g., 'US', 'GB')"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be updated without making actual changes"
        )

    def handle(self, *args, **options):
        country_code = options.get("country_code")
        dry_run = options.get("dry_run")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE: No changes will be made to the database"))

        if country_code:
            # Reconcile a single country
            self.handle_single_country(country_code, dry_run)
        else:
            # Reconcile all countries
            self.handle_all_countries(dry_run)

    def handle_single_country(self, country_code, dry_run=False):
        """Handle reconciliation of a single country."""
        self.stdout.write(f"Reconciling country with code: {country_code}")

        if dry_run:
            # Just show what would happen
            country_name = CountryService.get_country_name_by_code(country_code)
            if country_name:
                self.stdout.write(self.style.SUCCESS(f"Would update {country_code} -> {country_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"No mapping found for country code: {country_code}"))
            return

        # Actually reconcile the country
        result = CountryService.reconcile_single_country(country_code)

        if result["success"]:
            self.stdout.write(self.style.SUCCESS(result["message"]))
        else:
            self.stdout.write(self.style.ERROR(result["message"]))

    def handle_all_countries(self, dry_run=False):
        """Handle reconciliation of all countries."""
        if dry_run:
            self.stdout.write("Would reconcile all countries in the database")
            # For dry run, we would need to implement a dry-run version of the service
            # For now, just show the intention
            self.stdout.write(self.style.WARNING("Use without --dry-run to see actual results"))
            return

        self.stdout.write("Starting country reconciliation for all countries...")

        # Run the reconciliation service
        summary = CountryService.reconcile_country_names()

        # Display results
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("RECONCILIATION SUMMARY")
        self.stdout.write("=" * 50)

        self.stdout.write(f"Total countries processed: {summary['total_countries']}")

        if summary["updated_count"] > 0:
            self.stdout.write(self.style.SUCCESS(f"✓ Countries updated: {summary['updated_count']}"))

        if summary["already_named_count"] > 0:
            self.stdout.write(self.style.WARNING(f"→ Already had names: {summary['already_named_count']}"))

        if summary["not_found_count"] > 0:
            self.stdout.write(self.style.ERROR(f"✗ No mapping found: {summary['not_found_count']}"))
            if summary["not_found_codes"]:
                self.stdout.write(f"  Codes not found: {', '.join(summary['not_found_codes'])}")

        if summary["error_count"] > 0:
            self.stdout.write(self.style.ERROR(f"✗ Errors encountered: {summary['error_count']}"))

        # Final status
        if summary["error_count"] == 0 and summary["not_found_count"] == 0:
            self.stdout.write(self.style.SUCCESS("\n✓ Country reconciliation completed successfully!"))
        elif summary["updated_count"] > 0:
            self.stdout.write(self.style.WARNING("\n⚠ Country reconciliation completed with some issues."))
        else:
            self.stdout.write(self.style.ERROR("\n✗ Country reconciliation completed with errors."))
