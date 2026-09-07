from decimal import Decimal
from unittest import skipUnless

from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.test import RequestFactory, TestCase, TransactionTestCase

from shared.tests.schema import app_tip, migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from wallets.admin.wallet import WalletAdmin
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Transaction, Wallet
from wallets.serializers.wallet import WalletSerializer

POSTGRES = connection.vendor == "postgresql"
REASON = "the trigger is PostgreSQL only, and on SQLite none of these writes reaches a refusal"
FUNCTION = "transactions_user_account_is_derived"
UNIQUE_TX_PER_WALLET = "transactions_tx_hash_wallet_id_f1ecff24_uniq"


def _definition():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef(%s::regproc)", [FUNCTION])
        return cursor.fetchone()[0]


def _unique_indexes_touching(table, column):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s AND indexdef ILIKE '%%UNIQUE%%' "
            "AND indexdef LIKE %s",
            [table, f"%{column}%"],
        )
        return {name for (name,) in cursor.fetchall()}


@skipUnless(POSTGRES, REASON)
class ATransactionFollowsItsWalletAndWillNotChangeHandsTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("r17wallets")
        self.other = make_tenant("r17other")
        self.wallet = self.tenant.wallet
        self.transaction = self.tenant.transaction
        self.sibling = Wallet.objects.create(
            user_account=self.tenant.account,
            address="0x" + "51" * 20,
            chain=self.wallet.chain,
            wallet_type=self.wallet.wallet_type,
        )

    def test_an_ordinary_write_after_the_wallet_changes_hands_is_not_refused(self):
        Wallet.objects.filter(pk=self.wallet.pk).update(user_account=self.other.account)

        Transaction.objects.filter(pk=self.transaction.pk).update(amount=Decimal("2"))

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.user_account_id, self.other.account.uuid)

    def test_nothing_but_the_trigger_can_refuse_these_moves(self):
        for wallet in (self.sibling, self.other.wallet):
            with self.subTest(wallet=wallet.address):
                clash = Transaction.objects.filter(wallet=wallet, tx_hash=self.transaction.tx_hash)
                self.assertFalse(clash.exists())

        self.assertEqual(_unique_indexes_touching("transactions", "wallet_id"), {UNIQUE_TX_PER_WALLET})

    def test_moving_a_transaction_to_another_wallet_of_the_same_account_is_allowed(self):
        Transaction.objects.filter(pk=self.transaction.pk).update(wallet=self.sibling)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.wallet_id, self.sibling.uuid)
        self.assertEqual(self.transaction.user_account_id, self.tenant.account.uuid)


@skipUnless(POSTGRES, REASON)
class TheReverseRestoresTheBodyThatBehavesTest(TransactionTestCase):

    def tearDown(self):
        restore_every_migration()
        super().tearDown()

    def test_the_old_refusal_is_back_after_the_reverse_and_gone_after_the_forward(self):
        tenant = make_tenant("r17reverse")
        other = make_tenant("r17reverseother")

        migrate_to([("wallets", "0008_r0_owner_column")])
        self.assertIn("parent_account_id uuid;", _definition())
        Wallet.objects.filter(pk=tenant.wallet.pk).update(user_account=other.account)
        with self.assertRaises(Exception) as wedged:
            Transaction.objects.filter(pk=tenant.transaction.pk).update(amount=Decimal("3"))
        self.assertIn("does not match wallet.user_account_id", str(wedged.exception))

        migrate_to(app_tip("wallets"))
        Transaction.objects.filter(pk=tenant.transaction.pk).update(amount=Decimal("4"))
        tenant.transaction.refresh_from_db()
        self.assertEqual(tenant.transaction.user_account_id, other.account.uuid)


class TheVerifiedWalletIdentityIsReadOnlyInTheAdminTest(TestCase):

    def setUp(self):
        self.admin = WalletAdmin(Wallet, AdminSite())
        self.request = RequestFactory().get("/admin/")
        self.tenant = make_tenant("r17admin")

    def _serializer_would_refuse(self, wallet):
        elsewhere = make_tenant(f"r17elsewhere{wallet.pk.hex[:6]}").account
        return bool(WalletSerializer._verified_identity_change_errors(wallet, {"user_account": elsewhere}))

    def test_the_form_offers_the_field_exactly_when_the_serializer_would_accept_it(self):
        for wallet in (self.tenant.wallet, self.tenant.spare_wallet):
            with self.subTest(status=wallet.verification_status):
                read_only = "user_account" in self.admin.get_readonly_fields(self.request, wallet)

                self.assertEqual(read_only, self._serializer_would_refuse(wallet))

    def test_the_add_form_still_asks_for_the_account(self):
        self.assertNotIn("user_account", self.admin.get_readonly_fields(self.request, None))

    def test_a_pending_wallet_can_still_be_reassigned(self):
        pending = self.tenant.spare_wallet

        self.assertNotEqual(pending.verification_status, WALLET_VERIFICATION_STATUS_VERIFIED)
        self.assertNotIn("user_account", self.admin.get_readonly_fields(self.request, pending))

    def test_a_verified_wallet_cannot_be_reassigned_from_the_form(self):
        self.assertEqual(self.tenant.wallet.verification_status, WALLET_VERIFICATION_STATUS_VERIFIED)

        self.assertIn("user_account", self.admin.get_readonly_fields(self.request, self.tenant.wallet))
