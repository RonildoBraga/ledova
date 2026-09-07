from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
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
from tokens.services.register import token_register
from tokens.tasks.deployment import PENDING_DEPLOYMENT_AGE
from users.models import (
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
    UserAccount,
    UserProfile,
)
from wallets.models import Wallet
from whitelist.models import HolderType, WhitelistEntry, WhitelistStatus
from whitelist.querysets.entry import WhitelistEntryQuerySet
from whitelist.services.identity import ADDRESS_CHUNK

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
SHARED = Web3.to_checksum_address("0x" + "c3" * 20)
NAMELESS_ADDRESS = Web3.to_checksum_address("0x" + "e1" * 20)
AMBIGUOUS_ROW = "Allotment addresses with two wallets, so no member can be named"
UNIDENTIFIED_ROW = "Allotment addresses with no member behind them"


def _counts():
    return {row.label: row.count for row in worklist()}


def _checks():
    return {check.label: check for check in configuration_health()}


def _chain_reader(balances):
    reader = Mock()
    reader.deployment_block.return_value = 1
    reader.transfer_participants.return_value = set()
    reader.get_token_balance.side_effect = lambda contract, address: balances[address]
    reader.share_supply.return_value = (0, sum(balances.values()))
    return reader


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
            deployment_tx_hash="0x" + symbol.encode().hex().ljust(64, "0")[:64],
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
                "Allotment addresses with two wallets, so no member can be named": 0,
                "Allotment addresses with no member behind them": 1,
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

    def test_a_sold_out_offering_is_flagged_before_the_allotment_is_processed(self):
        token = self._token("CAP")
        offering = self._offering(token, OfferingStatus.APPROVED, cap=10)
        self._subscription(offering, SubscriptionStatus.PAID, quantity=10)

        counts = _counts()

        self.assertEqual(counts["Offerings at their cap and still open"], 1)
        self.assertEqual(counts["Subscriptions paid and not allotted"], 1)

    def test_an_unpaid_subscription_does_not_flag_an_offering_as_sold_out(self):
        token = self._token("UNP")
        offering = self._offering(token, OfferingStatus.APPROVED, cap=10)
        self._subscription(offering, SubscriptionStatus.AWAITING_PAYMENT, quantity=10)

        self.assertEqual(_counts()["Offerings at their cap and still open"], 0)

    def test_an_allotment_to_a_wallet_the_whitelist_can_name_is_not_flagged(self):
        token = self._token("WLT")
        WhitelistEntry.objects.create(wallet=self.wallet, status=WhitelistStatus.ACTIVE)
        ShareIssuance.objects.create(
            token=token, recipient_address=self.wallet.address, amount="10", status=IssuanceStatus.COMPLETED
        )

        counts = _counts()

        self.assertEqual(counts[AMBIGUOUS_ROW], 0)
        self.assertEqual(counts[UNIDENTIFIED_ROW], 0)

    def test_two_wallets_on_one_allotment_address_raise_the_red_queue(self):
        token = self._token("AMB")
        first = self._whitelisted_wallet("amb-one@example.test", "AMBONE", "Ann One", SHARED)
        second = self._whitelisted_wallet("amb-two@example.test", "AMBTWO", "Bob Two", SHARED)
        self.assertNotEqual(first.pk, second.pk)
        ShareIssuance.objects.create(
            token=token, recipient_address=SHARED, amount="25", status=IssuanceStatus.COMPLETED
        )

        counts = _counts()

        self.assertEqual(counts[AMBIGUOUS_ROW], 1)
        self.assertEqual(counts[UNIDENTIFIED_ROW], 0)
        register, _ = token_register(token, service=_chain_reader({SHARED: 25}))
        self.assertEqual([row["holder_type"] for row in register], [HolderType.AMBIGUOUS.value])

    def test_a_whitelisted_address_whose_wallet_names_nobody_raises_the_red_queue(self):
        token = self._token("NON")
        nameless = UserAccount.objects.create(account_number="NAMELESS")
        wallet = Wallet.objects.create(user_account=nameless, address=NAMELESS_ADDRESS, chain="base")
        WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE)
        ShareIssuance.objects.create(
            token=token, recipient_address=NAMELESS_ADDRESS, amount="40", status=IssuanceStatus.COMPLETED
        )

        counts = _counts()

        self.assertEqual(counts[UNIDENTIFIED_ROW], 1)
        register, _ = token_register(token, service=_chain_reader({NAMELESS_ADDRESS: 40}))
        self.assertEqual([row["holder_type"] for row in register], [HolderType.UNIDENTIFIED.value])

    def test_the_queue_is_never_smaller_than_the_register_it_stands_for(self):
        token = self._token("BTH")
        self._whitelisted_wallet("both-one@example.test", "BOTHONE", "Ann One", SHARED)
        self._whitelisted_wallet("both-two@example.test", "BOTHTWO", "Bob Two", SHARED)
        WhitelistEntry.objects.create(wallet=self.wallet, status=WhitelistStatus.ACTIVE)
        for address, amount in ((SHARED, "25"), (STRANGER, "10"), (self.wallet.address, "5")):
            ShareIssuance.objects.create(
                token=token, recipient_address=address, amount=amount, status=IssuanceStatus.COMPLETED
            )

        counts = _counts()
        reader = _chain_reader({SHARED: 25, STRANGER: 10, self.wallet.address: 5})
        rows, _ = token_register(token, service=reader)
        unnameable = [
            row for row in rows if row["holder_type"] in {HolderType.AMBIGUOUS.value, HolderType.UNIDENTIFIED.value}
        ]

        self.assertEqual(len(unnameable), 2)
        self.assertGreaterEqual(counts[AMBIGUOUS_ROW] + counts[UNIDENTIFIED_ROW], len(unnameable))

    def test_the_console_costs_the_same_whatever_the_register_holds_and_never_reads_the_chain(self):
        token = self._token("BIG")

        def allot(start, stop):
            for index in range(start, stop):
                ShareIssuance.objects.create(
                    token=token,
                    recipient_address=Web3.to_checksum_address(f"0x{index + 1:040x}"),
                    amount="1",
                    status=IssuanceStatus.COMPLETED,
                )

        with patch("tokens.services.share_token_service.ShareTokenService.get_token_balance") as balance:
            allot(0, 2)
            with CaptureQueriesContext(connection) as few:
                _counts()
            allot(2, 40)
            with CaptureQueriesContext(connection) as many:
                counts = _counts()

        self.assertEqual(counts[UNIDENTIFIED_ROW], 40)
        self.assertEqual(len(many), len(few))
        balance.assert_not_called()

    def test_the_identity_read_is_chunked_so_the_console_answers_on_a_deployment_of_many_addresses(self):
        token = self._token("MNY")
        addresses = [Web3.to_checksum_address(f"0x{index + 1:040x}") for index in range(11)]
        ShareIssuance.objects.bulk_create(
            ShareIssuance(token=token, recipient_address=address, amount="1", status=IssuanceStatus.COMPLETED)
            for address in addresses
        )
        self._whitelisted_wallet("many@example.test", "MANY", "Zoe Last", addresses[-1])

        with (
            patch("whitelist.services.identity.ADDRESS_CHUNK", 4),
            patch.object(
                WhitelistEntryQuerySet,
                "for_addresses",
                autospec=True,
                side_effect=WhitelistEntryQuerySet.for_addresses,
            ) as reads,
        ):
            counts = _counts()

        self.assertEqual(sorted(len(call.args[1]) for call in reads.call_args_list), [3, 4, 4])
        self.assertEqual(counts[UNIDENTIFIED_ROW], 10)
        self.assertEqual(counts[AMBIGUOUS_ROW], 0)
        self.assertLessEqual(ADDRESS_CHUNK, 1000)

    def _whitelisted_wallet(self, email, number, name, address):
        user = User.objects.create_user(email=email, password="pw-12345678")
        profile = UserProfile.objects.create(user=user, full_name=name)
        account = UserAccount.objects.create(account_number=number)
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(user_account=account, address=address, chain="base")
        return WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE)


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
