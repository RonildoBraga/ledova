from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from web3 import Web3

from assets.models import Asset, AssetChainDeployment
from companies.models import Company, CompanyStatus
from offerings.models import (
    Offering,
    OfferingExemption,
    OfferingStatus,
    Subscription,
    SubscriptionStatus,
)
from operators.models import Operator
from operators.services import configuration_health, worklist
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
)
from tokens.tasks.deployment import PENDING_DEPLOYMENT_AGE
from users.models import (
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
    UserAccount,
    UserProfile,
)
from wallets.models import Wallet
from whitelist.models import WhitelistEntry, WhitelistStatus

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
CONFIGURED = {
    "WHITELIST_CONTRACT_ADDRESS": "0x" + "1" * 40,
    "SHARE_TOKEN_FACTORY_ADDRESS": "0x" + "2" * 40,
}
STRANGER = Web3.to_checksum_address("0x" + "d4" * 20)


def _counts():
    return {row.label: row.count for row in worklist()}


def _checks():
    return {check.label: check for check in configuration_health()}


class WorklistTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="console-owner@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Console Pty Ltd", acn="900900900", status=CompanyStatus.ACTIVE
        )
        self.profile = UserProfile.objects.create(user=self.owner, full_name="Console Owner")
        self.account = UserAccount.objects.create(account_number="CONSOLE")
        self.account.user_profiles.add(self.profile)
        self.wallet = Wallet.objects.create(
            user_account=self.account, address=Web3.to_checksum_address("0x" + "a7" * 20), chain="base"
        )

    def _token(self, symbol, status=ShareTokenStatus.DEPLOYED):
        return ShareToken.objects.create(
            company=self.company,
            name=f"{symbol} shares",
            symbol=symbol,
            total_supply="10000",
            status=status,
            contract_address=Web3.to_checksum_address("0x" + symbol.encode().hex().ljust(40, "0")[:40]),
        )

    def _offering(self, token, status, cap=100, opens_at=None):
        return Offering.objects.create(
            token=token,
            status=status,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=Decimal("1.00"),
            minimum_shares=1,
            target_shares=min(10, cap),
            cap_shares=cap,
            opens_at=opens_at or timezone.now() - timedelta(days=1),
        )

    def _subscription(self, offering, status, quantity=1, issuance_request=None):
        return Subscription.objects.create(
            offering=offering,
            user_account=self.account,
            wallet=self.wallet,
            quantity=quantity,
            price_per_share=Decimal("1.00"),
            amount_due=Decimal(quantity),
            status=status,
            issuance_request=issuance_request,
        )

    def _request(self, token, status, amount=1):
        return ShareIssuanceRequest.objects.create(
            token=token, recipient_address=STRANGER, amount=amount, reason="Allotment", status=status
        )

    def test_every_row_is_zero_on_a_fresh_deployment(self):
        self.assertEqual(set(_counts().values()), {0})

    def test_every_row_counts_the_fixture_that_makes_it_non_zero(self):
        Company.objects.create(
            owner=self.owner, name="Applicant Pty Ltd", acn="111222333", status=CompanyStatus.SUBMITTED
        )
        InvestorClassification.objects.create(
            user_account=self.account,
            category=InvestorCategory.PROFESSIONAL_INVESTOR,
            status=InvestorClassificationStatus.SUBMITTED,
            declaration_accepted=True,
            declaration_text="Declared",
            submitted_at=timezone.now(),
        )
        under_review = self._token("URV")
        self._offering(under_review, OfferingStatus.SUBMITTED)

        full = self._token("FUL")
        full_offering = self._offering(full, OfferingStatus.APPROVED, cap=5)
        self._subscription(
            full_offering,
            SubscriptionStatus.ALLOTTED,
            quantity=5,
            issuance_request=self._request(full, RequestStatus.EXECUTED, amount=5),
        )

        open_offering = self._offering(self._token("OPN"), OfferingStatus.APPROVED, cap=1000)
        self._subscription(open_offering, SubscriptionStatus.AWAITING_PAYMENT)
        self._subscription(open_offering, SubscriptionStatus.PAID)
        broadcasting = self._token("BRD")
        self._subscription(
            self._offering(broadcasting, OfferingStatus.APPROVED),
            SubscriptionStatus.PAID,
            issuance_request=self._request(broadcasting, RequestStatus.EXECUTING),
        )

        WhitelistEntry.objects.create(address="0x" + "9" * 40, label="Pending", status=WhitelistStatus.PENDING)
        self._request(under_review, RequestStatus.SUBMITTED)
        CapitalIncreaseRequest.objects.create(
            token=under_review,
            additional_shares=10,
            new_authorized_total=10010,
            purpose="Growth",
            board_resolution_reference="BOARD-CONSOLE",
            status=RequestStatus.SUBMITTED,
        )
        stuck = self._token("STK", status=ShareTokenStatus.DEPLOYING)
        ShareToken.objects.filter(pk=stuck.pk).update(updated_at=timezone.now() - PENDING_DEPLOYMENT_AGE * 2)
        ShareIssuance.objects.create(
            token=under_review, recipient_address=STRANGER, amount="10", status=IssuanceStatus.COMPLETED
        )

        counts = _counts()

        self.assertEqual(
            counts,
            {
                "Company applications waiting": 1,
                "Investor classifications awaiting verification": 1,
                "Offerings awaiting review": 1,
                "Offerings at their cap and still open": 1,
                "Subscriptions awaiting payment": 1,
                "Subscriptions paid and not allotted": 1,
                "Subscriptions whose mint is broadcast and unresolved": 1,
                "Whitelist entries pending": 1,
                "Share issuance requests needing attention": 1,
                "Capital increase requests needing attention": 1,
                "Share tokens stuck deploying": 1,
                "Allotments to an address with no whitelist entry": 1,
            },
        )

    def test_a_broadcast_mint_that_failed_with_a_hash_still_counts(self):
        token = self._token("FLD")
        request = self._request(token, RequestStatus.FAILED)
        ShareIssuance.objects.create(
            token=token,
            recipient_address=STRANGER,
            amount="1",
            status=IssuanceStatus.FAILED,
            tx_hash="0x" + "f" * 64,
            idempotency_key=f"issuance-request:{request.uuid}",
        )
        self._subscription(
            self._offering(token, OfferingStatus.APPROVED), SubscriptionStatus.PAID, issuance_request=request
        )

        self.assertEqual(_counts()["Subscriptions whose mint is broadcast and unresolved"], 1)

    def test_an_allotment_to_a_whitelisted_wallet_is_not_flagged(self):
        token = self._token("WLT")
        WhitelistEntry.objects.create(wallet=self.wallet, status=WhitelistStatus.ACTIVE)
        ShareIssuance.objects.create(
            token=token, recipient_address=self.wallet.address, amount="10", status=IssuanceStatus.COMPLETED
        )

        self.assertEqual(_counts()["Allotments to an address with no whitelist entry"], 0)


@override_settings(STORAGES=TEST_STORAGES, **CONFIGURED)
class ConsolePageTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(email="console@example.test", password="pw-12345678"))

    def test_every_worklist_link_lands_on_a_changelist_the_operator_can_open(self):
        for row in worklist():
            with self.subTest(label=row.label):
                self.assertEqual(self.client.get(row.url).status_code, 200)

    def test_the_console_states_the_deployment_mode_and_who_keeps_each_register(self):
        owner = User.objects.create_user(email="listed@example.test", password="pw-12345678")
        Company.objects.create(owner=owner, name="Listed Pty Ltd", acn="777888999", status=CompanyStatus.ACTIVE)
        operator = Operator.get()
        operator.legal_name = "Ledova Operator Pty Ltd"
        operator.save(update_fields=["legal_name"])

        response = self.client.get(reverse("admin:operators_operator_changelist"))

        self.assertContains(response, "Registry (many companies on one instance)")
        self.assertContains(response, "Listed Pty Ltd")
        self.assertContains(response, "777888999")
        self.assertContains(response, "Ledova Operator Pty Ltd")
        self.assertContains(response, "does not decide who carries the section 168")


class ConfigurationHealthTest(TestCase):
    def setUp(self):
        self.operator = Operator.get()
        self.operator.name = "Ledova"
        self.operator.legal_name = "Ledova Operator Pty Ltd"
        self.operator.abn = "12345678901"
        self.operator.contact_email = "ops@example.test"
        self.operator.payment_reference_prefix = "LED"
        self.operator.save()
        self.asset = Asset.objects.create(symbol="TAUD", name="Test AUD", asset_type="stablecoin", decimals=2)
        AssetChainDeployment.objects.create(
            asset=self.asset, chain="base", contract_address="0x" + "5" * 40, decimals=2, is_active=True
        )
        self.operator.supported_settlement_assets.add(self.asset)

    @override_settings(**CONFIGURED)
    def test_a_configured_deployment_passes_every_check(self):
        self.assertTrue(all(check.ok for check in configuration_health()))

    @override_settings(**CONFIGURED)
    def test_an_incomplete_operator_row_fails_on_its_own(self):
        self.operator.contact_email = ""
        self.operator.save(update_fields=["contact_email"])

        checks = _checks()

        self.assertFalse(checks["Operator row"].ok)
        self.assertIn("contact_email", checks["Operator row"].detail)
        self.assertTrue(all(check.ok for label, check in checks.items() if label != "Operator row"))

    @override_settings(
        WHITELIST_CONTRACT_ADDRESS="", SHARE_TOKEN_FACTORY_ADDRESS=CONFIGURED["SHARE_TOKEN_FACTORY_ADDRESS"]
    )
    def test_a_missing_whitelist_contract_fails_on_its_own(self):
        checks = _checks()

        self.assertFalse(checks["WHITELIST_CONTRACT_ADDRESS"].ok)
        self.assertTrue(all(check.ok for label, check in checks.items() if label != "WHITELIST_CONTRACT_ADDRESS"))

    @override_settings(
        WHITELIST_CONTRACT_ADDRESS=CONFIGURED["WHITELIST_CONTRACT_ADDRESS"], SHARE_TOKEN_FACTORY_ADDRESS=""
    )
    def test_a_missing_factory_address_fails_on_its_own(self):
        checks = _checks()

        self.assertFalse(checks["SHARE_TOKEN_FACTORY_ADDRESS"].ok)
        self.assertTrue(all(check.ok for label, check in checks.items() if label != "SHARE_TOKEN_FACTORY_ADDRESS"))

    @override_settings(**CONFIGURED)
    def test_a_missing_prefix_and_an_over_long_one_each_fail_on_their_own(self):
        Operator.objects.filter(pk=self.operator.pk).update(payment_reference_prefix="")
        missing = _checks()
        self.assertFalse(missing["Payment reference prefix"].ok)
        self.assertIn("No payment reference prefix", missing["Payment reference prefix"].detail)

        Operator.objects.filter(pk=self.operator.pk).update(payment_reference_prefix="L" * 11)
        too_long = _checks()
        self.assertFalse(too_long["Payment reference prefix"].ok)
        self.assertIn("eighteen", too_long["Payment reference prefix"].detail)
        self.assertTrue(all(check.ok for label, check in too_long.items() if label != "Payment reference prefix"))

    @override_settings(**CONFIGURED)
    def test_an_empty_settlement_asset_set_fails_on_its_own(self):
        self.operator.supported_settlement_assets.clear()

        checks = _checks()

        self.assertFalse(checks["Settlement assets"].ok)
        self.assertIn("A fresh install starts this way", checks["Settlement assets"].detail)
        self.assertTrue(all(check.ok for label, check in checks.items() if label != "Settlement assets"))

    @override_settings(**CONFIGURED)
    def test_a_settlement_asset_with_no_deployment_on_the_receiving_chain_fails_on_its_own(self):
        AssetChainDeployment.objects.filter(asset=self.asset).update(is_active=False)

        checks = _checks()

        self.assertFalse(checks["Settlement assets"].ok)
        self.assertIn("TAUD has no active deployment on base", checks["Settlement assets"].detail)
        self.assertTrue(all(check.ok for label, check in checks.items() if label != "Settlement assets"))
