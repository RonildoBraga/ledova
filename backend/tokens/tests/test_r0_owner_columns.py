from datetime import timedelta
from unittest import skipUnless

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from tokens.exceptions import ChallengeUnknownException
from tokens.models import (
    CapitalIncreaseRequest,
    ShareIssuanceRequest,
    SigningChallenge,
    SigningChallengePurpose,
    SwapOrder,
)
from tokens.serializers.capital_increase import (
    CapitalIncreaseCreateSerializer,
    CapitalIncreaseDetailSerializer,
    CapitalIncreaseListSerializer,
    CapitalIncreaseUpdateSerializer,
)
from tokens.serializers.share_issuance_request import ShareIssuanceRequestSerializer
from tokens.serializers.swap_order import (
    SwapOrderDetailSerializer,
    SwapOrderListSerializer,
)
from tokens.services.signing_challenge import consume_challenge, issue_challenge

POSTGRES_ONLY = "The trigger is PostgreSQL; SQLite has no derive-and-refuse"
MIGRATION_ROUND_TRIP_ONLY = "Deferred constraint checks are PostgreSQL; SQLite queues nothing to settle"
BEFORE_THE_OWNER_COLUMNS = [("tokens", "0022_swap_nonce_is_unique")]
TABLE = "signing_challenges"
TRIGGER = "signing_challenges_wallet_is_checked"
SIGNATURE = "0x" + "ab" * 65


def orphan(challenge):
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(f"ALTER TABLE {TABLE} DISABLE TRIGGER {TRIGGER}")
        cursor.execute(f"UPDATE {TABLE} SET wallet_id = NULL WHERE digest = %s", [challenge.digest])
        if connection.vendor == "postgresql":
            cursor.execute(f"ALTER TABLE {TABLE} ENABLE TRIGGER {TRIGGER}")
    return SigningChallenge.objects.get(pk=challenge.pk)


class EveryRowCarriesItsOwnerTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("r0")

    def test_a_swap_carries_the_wallets_its_orders_name(self):
        swap = self.tenant.swap

        self.assertEqual(swap.seller_wallet_id, swap.sell_order.wallet_id)
        self.assertEqual(swap.buyer_wallet_id, swap.buy_order.wallet_id)

    def test_a_challenge_issued_for_an_order_carries_that_order_s_wallet(self):
        challenge = SigningChallenge.objects.create(
            purpose=SigningChallengePurpose.ORDER_CANCEL,
            wallet_address=self.tenant.wallet.address,
            chain_id=84532,
            verifying_contract="0x" + "b2" * 20,
            payload={},
            digest="0x" + "01" * 32,
            nonce=11,
            expires_at=timezone.now() + timedelta(minutes=5),
            order=self.tenant.order,
        )

        self.assertEqual(challenge.wallet_id, self.tenant.order.wallet_id)

    def test_a_capital_increase_carries_its_token_s_company(self):
        request = CapitalIncreaseRequest.objects.create(
            token=self.tenant.deployed_token, additional_shares=10, new_authorized_total=1010, purpose="r0"
        )

        self.assertEqual(request.company_id, self.tenant.deployed_token.company_id)

    def test_an_issuance_request_carries_its_token_s_company(self):
        request = ShareIssuanceRequest.objects.create(
            token=self.tenant.deployed_token,
            recipient_address="0x" + "cc" * 20,
            amount=5,
        )

        self.assertEqual(request.company_id, self.tenant.deployed_token.company_id)


class TheOwnerColumnsAreNotWritableThroughAnySerializerTest(TestCase):

    def test_no_serializer_over_these_models_exposes_the_owner_column(self):
        for serializer, column in (
            (SwapOrderListSerializer, "seller_wallet"),
            (SwapOrderDetailSerializer, "buyer_wallet"),
            (CapitalIncreaseListSerializer, "company"),
            (CapitalIncreaseDetailSerializer, "company"),
            (CapitalIncreaseCreateSerializer, "company"),
            (CapitalIncreaseUpdateSerializer, "company"),
            (ShareIssuanceRequestSerializer, "company"),
        ):
            with self.subTest(serializer=serializer.__name__):
                self.assertNotIn(column, serializer().fields)


@skipUnless(connection.vendor == "postgresql", POSTGRES_ONLY)
class TheTriggerRefusesWhatTheServiceDidNotSupplyTest(TransactionTestCase):

    def setUp(self):
        self.tenant = make_tenant("trigger")

    def a_challenge(self, **overrides):
        fields = {
            "purpose": SigningChallengePurpose.ORDER_CREATE,
            "wallet_address": self.tenant.wallet.address,
            "chain_id": 84532,
            "verifying_contract": "0x" + "b2" * 20,
            "payload": {},
            "digest": "0x" + "0f" * 32,
            "nonce": 22,
            "expires_at": timezone.now() + timedelta(minutes=5),
        }
        fields.update(overrides)
        return SigningChallenge(**fields)

    def test_a_challenge_with_no_wallet_is_refused(self):
        with self.assertRaises(Exception) as refusal:
            with transaction.atomic():
                SigningChallenge.objects.bulk_create([self.a_challenge()])

        self.assertIn("is required", str(refusal.exception))

    def test_a_wallet_whose_address_is_not_the_one_named_is_refused(self):
        other = make_tenant("other").wallet

        with self.assertRaises(Exception) as refusal:
            with transaction.atomic():
                self.a_challenge(wallet=other).save()

        self.assertIn("holds address", str(refusal.exception))

    def test_the_address_is_matched_without_regard_to_case(self):
        challenge = self.a_challenge(wallet=self.tenant.wallet, wallet_address=self.tenant.wallet.address.upper())

        challenge.save()

        self.assertEqual(SigningChallenge.objects.get(pk=challenge.pk).wallet_id, self.tenant.wallet.pk)

    def test_a_row_the_migration_could_not_resolve_cannot_be_written_again(self):
        challenge = self.a_legacy_challenge()

        with self.assertRaises(Exception) as refusal:
            with transaction.atomic():
                challenge.mark_consumed(SIGNATURE)

        self.assertIn("is required", str(refusal.exception))

    def a_legacy_challenge(self):
        challenge = self.a_challenge(wallet=self.tenant.wallet, digest="0x" + "1a" * 32)
        challenge.save()
        return orphan(challenge)

    def test_a_swap_cannot_name_a_wallet_its_order_does_not(self):
        other = make_tenant("stranger").wallet
        swap = self.tenant.swap

        with self.assertRaises(Exception) as refusal:
            with transaction.atomic():
                SwapOrder.objects.filter(pk=swap.pk).update(seller_wallet=other)

        self.assertIn("does not match", str(refusal.exception))

    def test_an_owner_column_cannot_change(self):
        request = CapitalIncreaseRequest.objects.create(
            token=self.tenant.deployed_token, additional_shares=10, new_authorized_total=1010, purpose="r0"
        )
        other = make_tenant("elsewhere").company

        with self.assertRaises(Exception) as refusal:
            with transaction.atomic():
                CapitalIncreaseRequest.objects.filter(pk=request.pk).update(company=other)

        self.assertIn("does not match", str(refusal.exception))


@skipUnless(connection.vendor == "postgresql", POSTGRES_ONLY)
class TheColumnsAreRequiredWhereThePathIsTest(TransactionTestCase):

    def test_the_derived_columns_are_not_nullable_and_the_challenge_one_is(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
                "WHERE (table_name, column_name) IN "
                "(('tokens_swaporder','seller_wallet_id'), ('tokens_swaporder','buyer_wallet_id'), "
                "('tokens_capitalincreaserequest','company_id'), ('tokens_shareissuancerequest','company_id'), "
                "('signing_challenges','wallet_id')) ORDER BY table_name, column_name"
            )
            rows = {(table, column): nullable for table, column, nullable in cursor.fetchall()}

        self.assertEqual(rows[("signing_challenges", "wallet_id")], "YES")
        for key, nullable in rows.items():
            if key != ("signing_challenges", "wallet_id"):
                self.assertEqual(nullable, "NO", key)


@skipUnless(connection.vendor == "postgresql", MIGRATION_ROUND_TRIP_ONLY)
class TheMigrationRoundTripsOnPopulatedTablesTest(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.tenant = make_tenant("roundtrip")
        self.seller = self.tenant.swap.sell_order.wallet_id
        self.buyer = self.tenant.swap.buy_order.wallet_id
        self.addCleanup(restore_every_migration)

    def test_a_table_that_gains_two_owner_columns_survives_the_round_trip(self):
        migrate_to(BEFORE_THE_OWNER_COLUMNS)
        restore_every_migration()

        swap = SwapOrder.objects.get(pk=self.tenant.swap.pk)
        self.assertEqual((swap.seller_wallet_id, swap.buyer_wallet_id), (self.seller, self.buyer))


class AChallengeWithNoOwnerIsNotOfferedForConsumptionTest(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.tenant = make_tenant("ownerless")
        self.challenge = orphan(
            issue_challenge(
                SigningChallengePurpose.ORDER_CREATE,
                self.tenant.wallet.address,
                {
                    "tokenUuid": str(self.tenant.deployed_token.uuid),
                    "orderType": "sell",
                    "quantity": 5,
                    "minQuantity": 0,
                    "pricePerShare": "2.50",
                },
                wallet=self.tenant.wallet,
            )
        )

    def consume(self):
        with transaction.atomic():
            consume_challenge(
                self.challenge.digest,
                SigningChallengePurpose.ORDER_CREATE,
                self.tenant.wallet.address,
                SIGNATURE,
            )

    def test_it_is_refused_as_unknown_rather_than_answered(self):
        with self.assertRaises(ChallengeUnknownException):
            self.consume()

    def test_it_is_left_unspent_rather_than_half_written(self):
        with self.assertRaises(ChallengeUnknownException):
            self.consume()

        self.challenge.refresh_from_db()
        self.assertIsNone(self.challenge.consumed_at)


class AChallengeCannotBeIssuedWithoutTheWalletItIsForTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("no-wallet")

    def fields(self):
        return {
            "tokenUuid": str(self.tenant.deployed_token.uuid),
            "orderType": "sell",
            "quantity": 5,
            "minQuantity": 0,
            "pricePerShare": "2.50",
        }

    def test_a_call_with_neither_an_order_nor_a_wallet_is_refused(self):
        with self.assertRaises(ValueError) as refusal:
            issue_challenge(SigningChallengePurpose.ORDER_CREATE, self.tenant.wallet.address, self.fields())

        self.assertIn("needs the wallet it is issued to", str(refusal.exception))
        self.assertFalse(SigningChallenge.objects.exists())

    def test_an_order_supplies_the_wallet_without_one_being_passed(self):
        challenge = issue_challenge(
            SigningChallengePurpose.ORDER_CANCEL,
            self.tenant.order.wallet.address,
            {"orderUuid": str(self.tenant.order.uuid)},
            order=self.tenant.order,
        )

        self.assertEqual(challenge.wallet_id, self.tenant.order.wallet_id)
