from django.contrib.auth import get_user_model
from django.db import IntegrityError, ProgrammingError, connection, transaction
from django.test import TestCase

from assets.models import Asset
from users.models import UserAccount, UserProfile
from wallets.models import Transaction, Wallet

User = get_user_model()

POSTGRES_ONLY = (
    "The derive-and-refuse trigger is PostgreSQL only: SQLite has no plpgsql, and the column exists "
    "for a PostgreSQL row-level security policy, so there is nothing on SQLite for it to protect."
)


def an_account(email):
    user = User.objects.create_user(email=email, password="pw-12345678")
    profile = UserProfile.objects.create(user=user)
    account = UserAccount.objects.create()
    account.user_profiles.add(profile)
    return account


def a_wallet(account, address):
    return Wallet.objects.create(user_account=account, address=address, chain="base", verification_status="VERIFIED")


class OwnerColumnIsDerivedInPythonTest(TestCase):

    def setUp(self):
        self.account = an_account("owner@example.test")
        self.wallet = a_wallet(self.account, "0x" + "a" * 40)
        self.asset = Asset.objects.create(symbol="QAT", name="QA Token", asset_type="tokenized_security", decimals=0)

    def _transaction(self, **overrides):
        fields = {"tx_hash": "0x" + "f" * 64, "chain": "base", "from_address": "0x" + "b" * 40}
        fields.update(overrides)
        return Transaction.objects.create(wallet=self.wallet, asset=self.asset, amount="1", **fields)

    def test_a_transaction_carries_its_wallets_account_without_being_told(self):
        row = self._transaction()

        self.assertEqual(row.user_account_id, self.account.pk)

    def test_update_or_create_fills_the_column_too(self):
        row, created = Transaction.objects.update_or_create(
            tx_hash="0x" + "e" * 64,
            wallet=self.wallet,
            defaults={"asset": self.asset, "amount": "2", "chain": "base", "from_address": "0x" + "b" * 40},
        )

        self.assertTrue(created)
        self.assertEqual(row.user_account_id, self.account.pk)

    def test_an_explicit_account_is_left_alone(self):
        row = self._transaction(user_account=self.account)

        self.assertEqual(row.user_account_id, self.account.pk)

    def test_the_column_is_not_in_the_api_representation(self):
        from wallets.serializers.transaction import TransactionSerializer

        self.assertNotIn("user_account", TransactionSerializer().fields)


class OwnerColumnTriggerTest(TestCase):

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest(POSTGRES_ONLY)
        self.account = an_account("triggered@example.test")
        self.wallet = a_wallet(self.account, "0x" + "a" * 40)
        self.stranger = an_account("stranger@example.test")
        self.stranger_wallet = a_wallet(self.stranger, "0x" + "c" * 40)
        self.asset = Asset.objects.create(symbol="QAT", name="QA Token", asset_type="tokenized_security", decimals=0)

    def _row(self, **overrides):
        fields = {"tx_hash": "0x" + "f" * 64, "chain": "base", "from_address": "0x" + "b" * 40}
        fields.update(overrides)
        return Transaction(wallet=self.wallet, asset=self.asset, amount="1", **fields)

    def test_bulk_create_bypasses_the_python_half_and_the_trigger_derives(self):
        row = self._row()
        Transaction.objects.bulk_create([row])

        self.assertEqual(Transaction.objects.get(pk=row.pk).user_account_id, self.account.pk)

    def test_a_mismatched_account_is_refused(self):
        with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
            with transaction.atomic():
                Transaction.objects.bulk_create([self._row(user_account=self.stranger)])

        self.assertIn("does not match wallet.user_account_id", str(raised.exception))

    def test_the_account_cannot_be_changed_after_the_row_exists(self):
        row = Transaction.objects.create(
            wallet=self.wallet,
            asset=self.asset,
            amount="1",
            tx_hash="0x" + "1" * 64,
            chain="base",
            from_address="0x" + "b" * 40,
        )

        with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    'UPDATE "transactions" SET user_account_id = %s WHERE uuid = %s',
                    [self.stranger.pk, row.pk],
                )

        self.assertIn("does not match wallet.user_account_id", str(raised.exception))

    def test_moving_a_transaction_to_another_accounts_wallet_is_refused(self):
        row = Transaction.objects.create(
            wallet=self.wallet,
            asset=self.asset,
            amount="1",
            tx_hash="0x" + "2" * 64,
            chain="base",
            from_address="0x" + "b" * 40,
        )

        with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    'UPDATE "transactions" SET wallet_id = %s WHERE uuid = %s',
                    [self.stranger_wallet.pk, row.pk],
                )

        self.assertIn("does not match wallet.user_account_id", str(raised.exception))

    def test_changing_the_wallet_and_the_account_together_is_still_refused(self):
        row = Transaction.objects.create(
            wallet=self.wallet,
            asset=self.asset,
            amount="1",
            tx_hash="0x" + "4" * 64,
            chain="base",
            from_address="0x" + "b" * 40,
        )

        with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    'UPDATE "transactions" SET wallet_id = %s, user_account_id = %s WHERE uuid = %s',
                    [self.stranger_wallet.pk, self.stranger.pk, row.pk],
                )

        self.assertIn("user_account_id cannot change", str(raised.exception))

    def test_nulling_the_account_is_repaired_rather_than_refused(self):
        row = Transaction.objects.create(
            wallet=self.wallet,
            asset=self.asset,
            amount="1",
            tx_hash="0x" + "5" * 64,
            chain="base",
            from_address="0x" + "b" * 40,
        )

        with connection.cursor() as cursor:
            cursor.execute('UPDATE "transactions" SET user_account_id = NULL WHERE uuid = %s', [row.pk])

        row.refresh_from_db()
        self.assertEqual(row.user_account_id, self.account.pk)

    def test_an_ordinary_update_still_works(self):
        row = Transaction.objects.create(
            wallet=self.wallet,
            asset=self.asset,
            amount="1",
            tx_hash="0x" + "3" * 64,
            chain="base",
            from_address="0x" + "b" * 40,
        )

        row.status = "confirmed"
        row.save(update_fields=["status"])
        row.refresh_from_db()

        self.assertEqual(row.status, "confirmed")
        self.assertEqual(row.user_account_id, self.account.pk)
