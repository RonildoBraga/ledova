from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from offerings.models import SettlementRail, Subscription
from offerings.tests.factories import forget_fixture_subscriptions
from shared.tests.tenants import make_tenant

TX_HASH = "0x" + "9" * 64


class SubscriptionConstraintTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("constraints")
        forget_fixture_subscriptions()
        self.stablecoin = self.tenant.refs.stablecoin

    def _build(self, **overrides):
        fields = {
            "offering": self.tenant.offering,
            "user_account": self.tenant.account,
            "wallet": self.tenant.wallet,
            "quantity": 10,
            "price_per_share": Decimal("2.50"),
            "amount_due": Decimal("25.00"),
        }
        fields.update(overrides)
        return Subscription(**fields)

    def _refuses(self, **overrides):
        with self.assertRaises(IntegrityError) as raised:
            with transaction.atomic():
                self._build(**overrides).save()
        return str(raised.exception)

    def _named(self, message, constraint, sqlite_fragment):
        self.assertIn(constraint if connection.vendor == "postgresql" else sqlite_fragment, message)

    def test_one_reference_belongs_to_one_subscription(self):
        self._build(reference="PAY4H7K9M2N").save()
        message = self._refuses(reference="PAY4H7K9M2N")
        self._named(message, "subscription_reference_unique", "offerings_subscription.reference")

    def test_any_number_of_subscriptions_carry_no_reference_yet(self):
        for _ in range(3):
            self._build(reference="").save()
        self.assertEqual(Subscription.objects.filter(reference="").count(), 3)

    def test_one_on_chain_transfer_cannot_fund_two_subscriptions(self):
        self._build(payment_tx_hash=TX_HASH).save()
        message = self._refuses(payment_tx_hash=TX_HASH)
        self._named(message, "subscription_payment_tx_hash_unique", "offerings_subscription.payment_tx_hash")
        self.assertEqual(Subscription.objects.filter(payment_tx_hash=TX_HASH).count(), 1)

    def test_any_number_of_subscriptions_carry_no_transfer_hash(self):
        for _ in range(3):
            self._build(payment_tx_hash="").save()
        self.assertEqual(Subscription.objects.filter(payment_tx_hash="").count(), 3)

    def test_a_subscription_asks_for_at_least_one_share(self):
        self._build(quantity=1).save()
        self.assertIn("subscription_quantity_positive", self._refuses(quantity=0))

    def test_an_allotment_never_passes_the_quantity_asked_for(self):
        self._build(quantity=10, allotted_quantity=10).save()
        self._build(quantity=10, allotted_quantity=0).save()
        self._build(quantity=10, allotted_quantity=None).save()
        self.assertIn("subscription_allotted_within_quantity", self._refuses(quantity=10, allotted_quantity=11))

    def test_the_rail_and_the_settlement_asset_must_agree(self):
        self._build(settlement_rail=SettlementRail.BANK_TRANSFER, settlement_asset=None).save()
        self._build(settlement_rail=SettlementRail.STABLECOIN, settlement_asset=self.stablecoin).save()
        self.assertIn(
            "subscription_rail_matches_settlement_asset",
            self._refuses(settlement_rail=SettlementRail.BANK_TRANSFER, settlement_asset=self.stablecoin),
        )
        self.assertIn(
            "subscription_rail_matches_settlement_asset",
            self._refuses(settlement_rail=SettlementRail.STABLECOIN, settlement_asset=None),
        )
