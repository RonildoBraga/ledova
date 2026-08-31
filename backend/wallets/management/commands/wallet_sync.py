"""
Management command to trigger wallet sync for all verified wallets.

Usage:
    python manage.py wallet_sync
"""

from django.core.management.base import BaseCommand

from wallets.tasks.sync import sync_all_wallets


class Command(BaseCommand):
    help = "Sync all verified wallets (fetches transactions and updates holdings)"

    def handle(self, *args, **options):  # noqa: ARG002
        self.stdout.write("Triggering wallet sync for all verified wallets...")

        result = sync_all_wallets()

        self.stdout.write(self.style.SUCCESS(f"Queued {result['queued']}/{result['total']} wallets for sync"))
