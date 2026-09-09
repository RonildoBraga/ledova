import os
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from companies.models import Company, CompanyStatus, CompanyType
from operators.models import Operator
from shared.db import atomic
from shared.seeds.demo import (
    DEMO_ACN,
    DEMO_ADMIN_EMAIL,
    DEMO_AUTHORIZED_SHARES,
    DEMO_COMPANY_NAME,
    DEMO_INVESTOR_ADDRESS,
    DEMO_INVESTOR_EMAIL,
    DEMO_INVESTOR_NAME,
    DEMO_ISSUER_ADDRESS,
    DEMO_OPERATOR_ACCOUNT_NUMBER,
    DEMO_OPERATOR_BANK_ACCOUNT_NAME,
    DEMO_OPERATOR_BSB,
    DEMO_OPERATOR_REFERENCE_PREFIX,
    DEMO_OWNER_EMAIL,
    DEMO_OWNER_NAME,
    DEMO_PASSWORD_ENV_VAR,
    DEMO_TOKEN_NAME,
    DEMO_TOKEN_SYMBOL,
)
from tokens.models import ShareToken
from tokens.models.choices import ShareTokenStatus
from users.constants import ACCOUNT_STATUS_ACTIVE
from users.models import (
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
    UserProfile,
)
from users.models.user_account import AccountRole
from users.services.setup import ensure_defaults
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet
from wallets.models.wallet import Blockchain
from whitelist.models import WhitelistEntry, WhitelistStatus

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Seed a browser-ready local demo: the operator row, a superuser, an active company with a draft "
        "share class and a verified issuer wallet, and an eligible investor with a whitelisted wallet. "
        "Writes no transactions to any chain."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=None,
            help=(
                f"Password for every seeded account. Falls back to ${DEMO_PASSWORD_ENV_VAR}, "
                "then to a generated one that is printed below."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even when DEBUG is off. This creates accounts with a known password.",
        )

    @atomic()
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed: DEBUG is off. This command creates accounts with a known password. "
                "Re-run with --force only against a throwaway database."
            )

        password = options["password"] or os.environ.get(DEMO_PASSWORD_ENV_VAR) or secrets.token_urlsafe(12)
        self.created = 0

        self._seed_operator()
        self._seed_user(DEMO_ADMIN_EMAIL, password, superuser=True)

        owner = self._seed_user(DEMO_OWNER_EMAIL, password)
        owner_account = self._prepare_account(owner, DEMO_OWNER_NAME, AccountRole.COMPANY)
        issuer_wallet = self._seed_wallet(owner_account, DEMO_ISSUER_ADDRESS)
        company = self._seed_company(owner, issuer_wallet)
        token = self._seed_share_token(company)

        investor = self._seed_user(DEMO_INVESTOR_EMAIL, password)
        investor_account = self._prepare_account(investor, DEMO_INVESTOR_NAME, AccountRole.INVESTOR)
        investor_wallet = self._seed_wallet(investor_account, DEMO_INVESTOR_ADDRESS)
        self._seed_classification(investor_account)
        self._seed_whitelist_entry(investor_wallet)

        if options["verbosity"] >= 1:
            self.stdout.write(self.style.SUCCESS(f"Seed complete: {self.created} created."))
            self._report(password, company, token)

    def _track(self, created):
        if created:
            self.created += 1
        return created

    def _seed_operator(self):
        operator = Operator.get()
        if operator.bank_account_name or operator.bank_bsb or operator.bank_account_number:
            return operator

        operator.bank_account_name = DEMO_OPERATOR_BANK_ACCOUNT_NAME
        operator.bank_bsb = DEMO_OPERATOR_BSB
        operator.bank_account_number = DEMO_OPERATOR_ACCOUNT_NUMBER
        operator.payment_reference_prefix = DEMO_OPERATOR_REFERENCE_PREFIX
        operator.full_clean()
        operator.save()
        self._track(True)
        return operator

    def _seed_user(self, email, password, superuser=False):
        user = User.objects.filter(email=email).first()
        if user is None:
            factory = User.objects.create_superuser if superuser else User.objects.create_user
            user = factory(email=email, password=password, is_active=True, is_email_verified=True)
            self._track(True)
            return user

        user.set_password(password)
        user.is_active = True
        user.is_email_verified = True
        user.save(update_fields=["password", "is_active", "is_email_verified"])
        return user

    def _prepare_account(self, user, full_name, role):
        profile, account, _, _ = ensure_defaults(user)

        UserProfile.objects.filter(pk=profile.pk).update(
            full_name=full_name,
            is_signup_completed=True,
            is_id_verified=True,
            terms_and_conditions=True,
        )
        account.role = role
        account.account_status = ACCOUNT_STATUS_ACTIVE
        account.save(update_fields=["role", "account_status"])
        return account

    def _seed_wallet(self, account, address):
        wallet, created = Wallet.objects.filter_by_address(address, chain=Blockchain.BASE.value).get_or_create(
            user_account=account,
            defaults={
                "address": address,
                "chain": Blockchain.BASE.value,
                "verification_status": WALLET_VERIFICATION_STATUS_VERIFIED,
                "verified_at": timezone.now(),
            },
        )
        self._track(created)
        return wallet

    def _seed_company(self, owner, issuer_wallet):
        existing = Company.objects.filter(acn=DEMO_ACN).first()
        if existing is not None and existing.owner_id != owner.id:
            raise CommandError(
                f"ACN {DEMO_ACN} already belongs to '{existing.name}', owned by someone other than "
                f"{owner.email}. Change DEMO_ACN in shared/seeds/demo.py or remove that company."
            )

        company, created = Company.objects.get_or_create(
            acn=DEMO_ACN,
            defaults={
                "owner": owner,
                "name": DEMO_COMPANY_NAME,
                "company_type": CompanyType.PROPRIETARY,
                "status": CompanyStatus.ACTIVE,
                "operator_wallet": issuer_wallet,
                "is_open_to_investors": True,
            },
        )
        self._track(created)
        if not created:
            company.status = CompanyStatus.ACTIVE
            company.operator_wallet = issuer_wallet
            company.is_open_to_investors = True
            company.save(update_fields=["status", "operator_wallet", "is_open_to_investors"])
        return company

    def _seed_share_token(self, company):
        token, created = ShareToken.objects.get_or_create(
            company=company,
            symbol=DEMO_TOKEN_SYMBOL,
            defaults={
                "name": DEMO_TOKEN_NAME,
                "total_supply": DEMO_AUTHORIZED_SHARES,
                "status": ShareTokenStatus.DRAFT,
            },
        )
        self._track(created)
        return token

    def _seed_classification(self, account):
        classification, created = InvestorClassification.objects.get_or_create(
            user_account=account,
            category=InvestorCategory.PROFESSIONAL_INVESTOR,
            defaults={
                "status": InvestorClassificationStatus.VERIFIED,
                "declaration_accepted": True,
                "declared_basis": "Seeded demo classification.",
                "submitted_at": timezone.now(),
                "reviewed_at": timezone.now(),
            },
        )
        self._track(created)
        if not created:
            classification.status = InvestorClassificationStatus.VERIFIED
            classification.expires_at = None
            classification.save(update_fields=["status", "expires_at"])
        return classification

    def _seed_whitelist_entry(self, wallet):
        entry, created = WhitelistEntry.objects.get_or_create(
            wallet=wallet,
            defaults={
                "status": WhitelistStatus.ACTIVE,
                "is_whitelisted": True,
                "notes": "Seeded demo entry. The database row only; nothing was written to a chain.",
            },
        )
        self._track(created)
        if not created:
            entry.status = WhitelistStatus.ACTIVE
            entry.is_whitelisted = True
            entry.save(update_fields=["status", "is_whitelisted"])
        return entry

    def _report(self, password, company, token):
        lines = [
            "",
            "  Dashboard   http://localhost:5174",
            "  Admin       http://localhost:8000/admin",
            "",
            f"  superuser   {DEMO_ADMIN_EMAIL}",
            f"  company     {DEMO_OWNER_EMAIL}    owns {company.name} ({company.get_status_display()})",
            f"  investor    {DEMO_INVESTOR_EMAIL}  verified wholesale, whitelisted",
            f"  password    {password}",
            "",
            f"  issuer wallet    {DEMO_ISSUER_ADDRESS}  (Hardhat account #0)",
            f"  investor wallet  {DEMO_INVESTOR_ADDRESS}  (Hardhat account #1)",
            "",
            f"  Share class {token.symbol} is {token.get_status_display().lower()}; the whitelist entry is a",
            "  database row only, so the investor is not whitelisted on any chain.",
            "  Deploying the token and minting to them write real transactions.",
        ]
        self.stdout.write("\n".join(lines))
