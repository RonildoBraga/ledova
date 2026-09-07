from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone
from web3 import Web3

from assets.models import Asset
from companies.models import Company, CompanyStatus
from offerings.models import Offering, OfferingExemption
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
    TransferOrder,
)
from tokens.models.choices import TransferOrderType
from users.models import UserAccount
from wallets.models import Wallet

User = get_user_model()

HOLDER = Web3.to_checksum_address("0x" + "a7" * 20)
CONTRACT = Web3.to_checksum_address("0x" + "e7" * 20)


class RegisterSpineProtectionTest(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(email="protect@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Protected Pty Ltd", acn="321321321", status=CompanyStatus.ACTIVE
        )
        self.token = ShareToken.objects.create(
            company=self.company,
            name="Protected ordinary shares",
            symbol="PRO",
            total_supply="10000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address=CONTRACT,
        )

    def _issuance(self):
        return ShareIssuance.objects.create(
            token=self.token,
            recipient_address=HOLDER,
            amount="100",
            status=IssuanceStatus.COMPLETED,
            completed_at=timezone.now(),
        )

    def _offering(self):
        return Offering.objects.create(
            token=self.token,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=Decimal("2.50"),
            minimum_shares=1,
            target_shares=10,
            cap_shares=1000,
            opens_at=timezone.now() - timedelta(days=1),
        )

    def _transfer_order(self):
        account = UserAccount.objects.create(account_number="PROTECT-1")
        wallet = Wallet.objects.create(user_account=account, address=HOLDER, chain="base")
        asset = Asset.objects.create(symbol="PUSD", name="Protected dollar", asset_type="stablecoin", decimals=2)
        return TransferOrder.objects.create(
            token=self.token,
            payment_asset=asset,
            wallet=wallet,
            owner_account=account,
            wallet_address=wallet.address,
            order_type=TransferOrderType.SELL,
            quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def _protected(self, deletable):
        with self.assertRaises(ProtectedError):
            deletable.delete()

    def test_a_company_cannot_take_its_share_class_with_it(self):
        self._protected(self.company)

        self.assertTrue(ShareToken.objects.filter(pk=self.token.pk).exists())
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_a_share_class_cannot_take_its_issuances_with_it(self):
        issuance = self._issuance()

        self._protected(self.token)

        self.assertTrue(ShareIssuance.objects.filter(pk=issuance.pk).exists())

    def test_a_share_class_cannot_take_its_issuance_requests_with_it(self):
        request = ShareIssuanceRequest.objects.create(
            token=self.token, recipient_address=HOLDER, amount=100, reason="Allotment"
        )

        self._protected(self.token)

        self.assertTrue(ShareIssuanceRequest.objects.filter(pk=request.pk).exists())

    def test_a_share_class_cannot_take_its_capital_increase_requests_with_it(self):
        request = CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=100,
            new_authorized_total=10100,
            purpose="Growth",
            board_resolution_reference="BOARD-1",
        )

        self._protected(self.token)

        self.assertTrue(CapitalIncreaseRequest.objects.filter(pk=request.pk).exists())

    def test_a_share_class_cannot_take_its_offerings_with_it(self):
        offering = self._offering()

        self._protected(self.token)

        self.assertTrue(Offering.objects.filter(pk=offering.pk).exists())

    def test_a_share_class_cannot_take_its_transfer_orders_with_it(self):
        order = self._transfer_order()

        self._protected(self.token)

        self.assertTrue(TransferOrder.objects.filter(pk=order.pk).exists())

    def test_a_share_class_with_nothing_behind_it_is_still_deletable(self):
        self.token.delete()

        self.assertFalse(ShareToken.objects.filter(pk=self.token.pk).exists())
