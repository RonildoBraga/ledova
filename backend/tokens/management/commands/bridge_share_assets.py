from django.core.management.base import BaseCommand

from tokens.models import ShareToken
from tokens.services import ShareTokenService


class Command(BaseCommand):
    help = "Write the verified Asset and chain deployment for share tokens deployed before the bridge existed"

    def add_arguments(self, parser):
        parser.add_argument("--symbol", help="Bridge only the share classes with this symbol")
        parser.add_argument("--dry-run", action="store_true", help="List what would be bridged and write nothing")

    def handle(self, *args, **options):
        tokens = ShareToken.objects.deployed_with_contract().select_related("company").order_by("created_at")
        if options["symbol"]:
            tokens = tokens.filter(symbol=options["symbol"])

        service = ShareTokenService() if not options["dry_run"] else None
        for token in tokens:
            label = f"{token.company.name} {token.symbol} at {token.contract_address}"
            if options["dry_run"]:
                self.stdout.write(f"would bridge {label}")
                continue
            service.bridge_share_asset(token, token.contract_address)
            self.stdout.write(self.style.SUCCESS(f"bridged {label}"))

        self.stdout.write(f"{tokens.count()} deployed share token(s) considered")
