from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.db import DatabaseError, IntegrityError, connections
from django.test import TestCase, TransactionTestCase, override_settings
from eth_account.messages import encode_typed_data
from rest_framework.test import APIClient, APITransactionTestCase

from feature_flags.models import FeatureFlag
from shared.db import atomic, current_alias, reset_principal, use_operator
from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from tokens.models import (
    SwapOrder,
    SwapOrderStatus,
    TransferOrder,
    TransferOrderStatus,
    TransferOrderType,
)
from tokens.services.atomic_swap_service import AtomicSwapService
from tokens.services.settlement_context import capture_settlement_context
from tokens.tests.swap_state_fixtures import (
    BUYER,
    CONTRACT,
    SELLER,
    make_swap,
    swap_service,
)
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet

IS_POSTGRES = settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)
BEFORE = [("tokens", "0039_swap_settlement_context")]
AFTER = [("tokens", "0040_swap_parent_identity")]
MIGRATION = import_module("tokens.migrations.0040_swap_parent_identity")


OUTSIDER_ADDRESS = "0x" + "9c" * 20


@skipUnless(IS_POSTGRES, "Requires the actual PostgreSQL parent guards")
@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
class SwapParentStorageTest(TestCase):
    def test_owner_tuple_changes_refuse_including_a_coherent_reassignment(self):
        swap = make_swap("parent-owner")
        other = make_tenant("parent-new-owner", with_swap=False)
        order = swap.sell_order
        before = TransferOrder.objects.filter(pk=order.pk).values().get()
        for changes in (
            {"uuid": uuid4()},
            {"owner_account_id": other.account.pk},
            {"wallet_id": other.wallet.pk},
            {"wallet_address": other.wallet.address},
            {
                "owner_account_id": other.account.pk,
                "wallet_id": other.wallet.pk,
                "wallet_address": other.wallet.address,
            },
        ):
            with self.subTest(fields=sorted(changes)), self.assertRaisesMessage(
                IntegrityError, "An order owner identity cannot change"
            ), atomic():
                TransferOrder.objects.filter(pk=order.pk).update(**changes)
            self.assertEqual(TransferOrder.objects.filter(pk=order.pk).values().get(), before)

    def test_case_spelling_and_existing_economic_status_and_payment_writes_survive(self):
        tenant = make_tenant("parent-allowed", with_swap=False)
        order = tenant.order
        TransferOrder.objects.filter(pk=order.pk).update(wallet_address=order.wallet_address.upper())
        with use_operator():
            order.refresh_from_db()
        self.assertEqual(order.wallet_address, tenant.wallet.address.upper())
        order.quantity = 12
        order.min_quantity = 2
        order.price_per_share = "2.00"
        order.payment_asset = None
        order.save()
        order.cancel()
        with use_operator():
            order.refresh_from_db()
        self.assertEqual((order.quantity, order.min_quantity, order.status), (12, 2, TransferOrderStatus.CANCELLED))
        self.assertIsNone(order.payment_asset_id)
        swap = make_swap("parent-in-place")
        SwapOrder.objects.filter(pk=swap.pk).update(status=SwapOrderStatus.EXECUTING, error_message="unresolved")
        with use_operator():
            swap.refresh_from_db()
        self.assertEqual((swap.status, swap.error_message), (SwapOrderStatus.EXECUTING, "unresolved"))

    def test_referenced_parent_delete_cannot_be_deferred_until_a_replacement_insert(self):
        swap = make_swap("parent-replacement")
        row = TransferOrder.objects.filter(pk=swap.sell_order_id).values().get()
        with self.assertRaises(IntegrityError), atomic():
            with connections[current_alias()].cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL DEFERRED")
                cursor.execute("DELETE FROM tokens_transferorder WHERE uuid = %s", [swap.sell_order_id])
            self.fail("The referenced parent DELETE must fail before a replacement can be inserted")
        self.assertEqual(TransferOrder.objects.filter(pk=swap.sell_order_id).values().get(), row)
        self.assertTrue(SwapOrder.objects.filter(pk=swap.pk).exists())

    def test_an_unreferenced_order_remains_deletable_and_retained_v1_does_not(self):
        tenant = make_tenant("parent-delete", with_swap=False)
        order_id = tenant.order.pk
        tenant.order.delete()
        self.assertFalse(TransferOrder.objects.filter(pk=order_id).exists())
        swap = make_swap("parent-retained")
        with self.assertRaisesMessage(IntegrityError, "cannot be deleted"), atomic():
            swap.sell_order.delete()
        self.assertTrue(TransferOrder.objects.filter(pk=swap.sell_order_id).exists())
        self.assertTrue(SwapOrder.objects.filter(pk=swap.pk).exists())

    def test_only_two_parent_constraints_restrict_deletes_and_no_function_gains_privilege(self):
        with connections[current_alias()].cursor() as cursor:
            cursor.execute(
                "SELECT a.attname, c.confdeltype, c.condeferrable, c.condeferred "
                "FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
                "WHERE c.contype = 'f' AND c.conrelid = 'tokens_swaporder'::regclass "
                "AND c.confrelid = 'tokens_transferorder'::regclass ORDER BY a.attname"
            )
            self.assertEqual(
                cursor.fetchall(), [("buy_order_id", "r", False, False), ("sell_order_id", "r", False, False)]
            )
            cursor.execute(
                "SELECT proname, prosecdef FROM pg_proc WHERE proname IN "
                "('tokens_swap_has_current_party', 'tokens_swaporder_seller_wallet_id_is_derived', "
                "'tokens_swaporder_buyer_wallet_id_is_derived') ORDER BY proname"
            )
            functions = cursor.fetchall()
        self.assertEqual(len(functions), 3)
        self.assertTrue(all(not privileged for _name, privileged in functions))


@skipUnless(IS_POSTGRES, "Requires actual PostgreSQL foreign-key metadata")
class SwapParentForeignKeyMetadataTest(TransactionTestCase):
    def test_unexpected_reference_or_validation_state_refuses_without_replacing_either_constraint(self):
        connection = connections[current_alias()]
        for referenced, validated in (("alternate", True), ("uuid", False), ("uuid", True)):
            with self.subTest(referenced=referenced, validated=validated), connection.schema_editor() as editor:
                editor.execute("CREATE TEMP TABLE tokens_transferorder (uuid uuid PRIMARY KEY, alternate uuid UNIQUE)")
                editor.execute("CREATE TEMP TABLE tokens_swaporder (sell_order_id uuid, buy_order_id uuid)")
                try:
                    for column in ("sell_order_id", "buy_order_id"):
                        validation = "" if validated else " NOT VALID"
                        editor.execute(
                            f"ALTER TABLE pg_temp.tokens_swaporder ADD CONSTRAINT {column}_parent "
                            f"FOREIGN KEY ({column}) REFERENCES pg_temp.tokens_transferorder ({referenced}) "
                            f"DEFERRABLE INITIALLY DEFERRED{validation}"
                        )
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE conrelid = 'pg_temp.tokens_swaporder'::regclass ORDER BY conname"
                        )
                        before = cursor.fetchall()
                    if referenced != "uuid" or not validated:
                        with self.assertRaisesMessage(RuntimeError, "Unexpected swap-to-order foreign keys"):
                            MIGRATION.replace_parent_foreign_keys(editor, True)
                    else:
                        MIGRATION.replace_parent_foreign_keys(editor, True)
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT confdeltype, condeferrable FROM pg_constraint "
                                "WHERE conrelid = 'pg_temp.tokens_swaporder'::regclass"
                            )
                            self.assertEqual(cursor.fetchall(), [("r", False), ("r", False)])
                        MIGRATION.replace_parent_foreign_keys(editor, False)
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE conrelid = 'pg_temp.tokens_swaporder'::regclass ORDER BY conname"
                        )
                        self.assertEqual(cursor.fetchall(), before)
                finally:
                    editor.execute("DROP TABLE pg_temp.tokens_swaporder")
                    editor.execute("DROP TABLE pg_temp.tokens_transferorder")


@skipUnless(MIGRATIONS_ENABLED, "Requires actual parent-identity migrations")
@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
class SwapParentMigrationTest(TransactionTestCase):
    def setUp(self):
        self.swap = make_swap("parent-migration")
        self.parent = self.swap.sell_order
        self.parent_before = TransferOrder.objects.filter(pk=self.parent.pk).values().get()
        self.old_apps = migrate_to(BEFORE)
        self.addCleanup(self.restore)

    def restore(self):
        if self.old_apps:
            migrate_to(BEFORE)
            self.old_apps.get_model("tokens", "TransferOrder").objects.filter(pk=self.parent.pk).update(
                **{k: v for k, v in self.parent_before.items() if k != "uuid"}
            )
        restore_every_migration()

    def test_preflight_refuses_wallet_and_captured_owner_drift_without_rewriting_rows(self):
        other = make_tenant("parent-drift-target", with_swap=False)
        orders = self.old_apps.get_model("tokens", "TransferOrder").objects
        swaps = self.old_apps.get_model("tokens", "SwapOrder").objects
        for changes, reason in (
            ({"wallet_id": other.wallet.pk}, "seller wallet differs"),
            ({"owner_account_id": other.account.pk}, "seller captured owner differs"),
            ({"wallet_address": other.wallet.address}, "seller captured owner differs"),
        ):
            with self.subTest(reason=reason):
                orders.filter(pk=self.parent.pk).update(**changes)
                try:
                    order_before = orders.filter(pk=self.parent.pk).values().get()
                    swap_before = swaps.filter(pk=self.swap.pk).values().get()
                    with self.assertRaises(RuntimeError) as refused:
                        migrate_to(AFTER)
                    self.assertIn(reason, str(refused.exception))
                    self.assertIn(str(self.swap.pk), str(refused.exception))
                    self.assertEqual(orders.filter(pk=self.parent.pk).values().get(), order_before)
                    self.assertEqual(swaps.filter(pk=self.swap.pk).values().get(), swap_before)
                finally:
                    migrate_to(BEFORE)
                    orders.filter(pk=self.parent.pk).update(**{k: self.parent_before[k] for k in changes})
        migrate_to(AFTER)

    def test_valid_v1_history_survives_retired_verification_and_membership(self):
        Wallet.objects.filter(pk=self.swap.seller_wallet_id).update(verification_status="UNVERIFIED")
        self.parent.owner_account.user_profiles.clear()
        swaps = self.old_apps.get_model("tokens", "SwapOrder").objects
        orders = self.old_apps.get_model("tokens", "TransferOrder").objects
        before = list(swaps.order_by("pk").values()), list(orders.order_by("pk").values())
        migrate_to(AFTER)
        self.assertEqual((list(swaps.order_by("pk").values()), list(orders.order_by("pk").values())), before)

    def test_legacy_child_first_deletion_and_both_visible_updates_keep_original_behavior(self):
        self.old_apps = migrate_to([("tokens", "0038_order_action_submissions")])
        restore_every_migration()
        with use_operator():
            self.swap.refresh_from_db()
        self.assertEqual(self.swap.settlement_protocol_version, 0)
        self.assertIsNone(self.swap.settlement_context)
        SwapOrder.objects.filter(pk=self.swap.pk).update(
            seller_signature="legacy", status=SwapOrderStatus.SELLER_SIGNED
        )
        with use_operator():
            self.swap.refresh_from_db()
        self.assertEqual(self.swap.seller_signature, "legacy")
        parent_id = self.parent.pk
        self.parent.delete()
        self.assertFalse(SwapOrder.objects.filter(pk=self.swap.pk).exists())
        self.assertFalse(TransferOrder.objects.filter(pk=parent_id).exists())
        self.old_apps = None


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "33" * 32)
class ScopedSwapParentIdentityTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        with use_operator():
            self.parties = {
                "seller": make_tenant("private-seller", with_swap=False),
                "buyer": make_tenant("private-buyer", with_swap=False),
            }
            self.orders = {}
            for role, key, kind in (
                ("seller", SELLER, TransferOrderType.SELL),
                ("buyer", BUYER, TransferOrderType.BUY),
            ):
                tenant = self.parties[role]
                wallet = Wallet.objects.create(
                    user_account=tenant.account,
                    address=key.address,
                    chain="base",
                    verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
                )
                self.orders[role] = TransferOrder.objects.create(
                    token=self.parties["seller"].deployed_token,
                    payment_asset=tenant.refs.stablecoin,
                    wallet=wallet,
                    owner_account=tenant.account,
                    wallet_address=wallet.address,
                    order_type=kind,
                    quantity=40,
                    filled_quantity=10,
                    price_per_share="1.50",
                    status=TransferOrderStatus.PARTIALLY_FILLED,
                )
            self.swap = AtomicSwapService().create_swap_order(
                self.orders["seller"], self.orders["buyer"], share_amount=10
            )
            FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.client = APIClient()
        event = patch("tokens.services.atomic_swap_service.publish_trading_event")
        self.event = event.start()
        self.addCleanup(event.stop)
        self.choose_caller("seller")

    def choose_caller(self, role):
        self.caller = role
        self.signed_in_as(self.parties[role].user)
        order = self.orders[role]
        self.url = f"/api/v1/trading/orders/{order.pk}/swap/"
        self.identity = {
            "swap_uuid": str(self.swap.pk),
            "owner_account_uuid": str(order.owner_account_id),
            "wallet_uuid": str(order.wallet_id),
            "settlement_digest": self.swap.settlement_digest,
        }

    def assert_private_boundary(self):
        self.the_principal_the_middleware_would_set(self.parties[self.caller].user)
        other = "buyer" if self.caller == "seller" else "seller"
        self.assertTrue(TransferOrder.objects.filter(pk=self.orders[self.caller].pk).exists())
        self.assertTrue(Wallet.objects.filter(pk=self.orders[self.caller].wallet_id).exists())
        self.assertFalse(TransferOrder.objects.filter(pk=self.orders[other].pk).exists())
        self.assertFalse(Wallet.objects.filter(pk=self.orders[other].wallet_id).exists())
        with connections[current_alias()].cursor() as cursor:
            cursor.execute("SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            role, bypass = cursor.fetchone()
        self.assertEqual(role, settings.RLS_ROLES["app"])
        self.assertFalse(bypass)

    def signature(self, role):
        key = SELLER if role == "seller" else BUYER
        return (
            "0x"
            + key.sign_message(
                encode_typed_data(full_message=self.swap.settlement_context["typed_data"])
            ).signature.hex()
        )

    def post_signature(self, role):
        key = SELLER if role == "seller" else BUYER
        return self.client.post(
            self.url + "sign/",
            {**self.identity, "signer_address": key.address, "signature": self.signature(role)},
            format="json",
        )

    def test_either_caller_can_relay_either_captured_first_signature_without_private_parent_reads(self):
        for caller in ("seller", "buyer"):
            for signer in ("seller", "buyer"):
                with self.subTest(caller=caller, signer=signer):
                    with use_operator():
                        self.swap = AtomicSwapService().create_swap_order(
                            self.orders["seller"], self.orders["buyer"], share_amount=10
                        )
                    self.choose_caller(caller)
                    self.assert_private_boundary()
                    lookup = self.client.get(self.url, self.identity)
                    self.assertEqual(lookup.status_code, 200, lookup.content)
                    self.event.reset_mock()
                    response = self.post_signature(signer)
                    self.assertEqual(response.status_code, 200, response.content)
                    with use_operator():
                        self.swap.refresh_from_db()
                    self.assertEqual(getattr(self.swap, f"{signer}_signature"), self.signature(signer))
                    self.assertEqual(self.event.call_count, 1)
                    replay = self.post_signature(signer)
                    self.assertEqual(replay.status_code, 200, replay.content)
                    self.assertEqual(self.event.call_count, 1)
                    self.assert_private_boundary()

    def test_second_signature_and_claim_persist_but_invisible_parent_outcome_remains_unresolved(self):
        first = self.post_signature("buyer")
        self.assertEqual(first.status_code, 200, first.content)
        service = swap_service()
        with patch("tokens.views.trading_order.AtomicSwapService", return_value=service), patch.object(
            service, "execute_swap"
        ) as execute:
            second = self.post_signature("seller")
        self.assertEqual(second.status_code, 200, second.content)
        execute.assert_called_once()
        self.choose_caller(self.caller)
        with use_operator():
            claimed, transaction = service._claim_execution(self.swap.pk)
        self.assertEqual(claimed.status, SwapOrderStatus.EXECUTING)
        self.assertEqual(claimed.transaction_id, transaction.pk)
        service._record_never_sent(claimed, transaction, "synthetic failure", "Synthetic refusal")
        with use_operator():
            claimed.refresh_from_db()
        self.assertEqual(claimed.status, SwapOrderStatus.EXECUTING)
        with use_operator():
            self.assertEqual(TransferOrder.objects.get(pk=self.orders["seller"].pk).filled_quantity, 10)
            self.assertEqual(TransferOrder.objects.get(pk=self.orders["buyer"].pk).filled_quantity, 10)
        self.assert_private_boundary()

    def test_direct_database_refuses_outsider_and_copied_address_without_route_admission(self):
        with use_operator():
            outsider = make_tenant("private-outsider", with_swap=False)
            Wallet.objects.create(
                user_account=outsider.account,
                address=SELLER.address,
                chain="base",
                verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
            )
        self.signed_in_as(outsider.user)
        self.assertEqual(SwapOrder.objects.filter(pk=self.swap.pk).update(seller_signature=self.signature("seller")), 0)

        self.choose_caller("buyer")
        self.assert_private_boundary()
        with self.assertRaises(DatabaseError), atomic():
            SwapOrder.objects.filter(pk=self.swap.pk).update(seller_signature=self.signature("seller"))

        with use_operator():
            self.swap.refresh_from_db()
        self.assertFalse(self.swap.seller_signature)

        with use_operator(), self.assertRaises(DatabaseError), atomic():
            SwapOrder.objects.filter(pk=self.swap.pk).update(seller_address=OUTSIDER_ADDRESS)

    def test_direct_database_refuses_missing_principal_and_retired_verification_then_accepts_restoration(self):
        self.no_principal_is_set()
        self.assertEqual(SwapOrder.objects.filter(pk=self.swap.pk).update(buyer_signature=self.signature("buyer")), 0)

        self.choose_caller("seller")
        with self.assertRaises(DatabaseError), atomic():
            SwapOrder.objects.filter(pk=self.swap.pk).update(buyer_signature=self.signature("buyer"))

        with use_operator():
            Wallet.objects.filter(pk=self.orders["seller"].wallet_id).update(verification_status="UNVERIFIED")
        with self.assertRaises(DatabaseError), atomic():
            SwapOrder.objects.filter(pk=self.swap.pk).update(buyer_signature=self.signature("buyer"))

        with use_operator():
            Wallet.objects.filter(pk=self.orders["seller"].wallet_id).update(
                verification_status=WALLET_VERIFICATION_STATUS_VERIFIED
            )
            self.swap.refresh_from_db()
        self.assertFalse(self.swap.buyer_signature)

    def test_scoped_coherent_parent_reassignment_is_refused_before_an_otherwise_legal_owner_write(self):
        with use_operator():
            other = Wallet.objects.create(
                user_account=self.parties["seller"].account,
                address="0x" + "84" * 20,
                chain="base",
                verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
            )
        self.assertTrue(Wallet.objects.visible_to_user(self.parties["seller"].user).filter(pk=other.pk).exists())
        control = TransferOrder.objects.create(
            token=self.orders["seller"].token,
            owner_account_id=other.user_account_id,
            wallet=other,
            wallet_address=other.address,
            order_type=TransferOrderType.SELL,
            quantity=2,
            price_per_share="1.50",
        )
        self.assertTrue(
            TransferOrder.objects.visible_to_user(self.parties["seller"].user).filter(pk=control.pk).exists()
        )
        with self.assertRaisesMessage(IntegrityError, "An order owner identity cannot change"), atomic():
            TransferOrder.objects.filter(pk=self.orders["seller"].pk).update(wallet=other, wallet_address=other.address)
        self.assertEqual(TransferOrder.objects.get(pk=self.orders["seller"].pk).wallet_id, self.swap.seller_wallet_id)

    def test_current_chain_address_and_payment_binding_refuse_but_captured_null_payment_is_legal(self):
        wallet_id = self.orders["seller"].wallet_id
        order_id = self.orders["seller"].pk
        for model, pk, changes, restore in (
            (Wallet, wallet_id, {"chain": "polygon"}, {"chain": "base"}),
            (Wallet, wallet_id, {"address": "0x" + "85" * 20}, {"address": SELLER.address}),
            (TransferOrder, order_id, {"payment_asset": None}, {"payment_asset_id": self.swap.payment_asset_id}),
        ):
            with self.subTest(changes=changes):
                with use_operator():
                    model.objects.filter(pk=pk).update(**changes)
                try:
                    with self.assertRaises(DatabaseError), atomic():
                        SwapOrder.objects.filter(pk=self.swap.pk).update(buyer_signature=self.signature("buyer"))
                finally:
                    with use_operator():
                        model.objects.filter(pk=pk).update(**restore)
        with use_operator():
            TransferOrder.objects.filter(pk=order_id).update(payment_asset=None)
            self.swap = AtomicSwapService().create_swap_order(
                self.orders["seller"], self.orders["buyer"], share_amount=10
            )
        self.choose_caller("seller")
        self.assertIsNone(self.swap.settlement_context["seller"]["payment_asset_uuid"])
        self.assertEqual(self.post_signature("buyer").status_code, 200)

    def test_new_private_parent_insert_remains_refused_with_a_valid_snapshot(self):
        with use_operator():
            values = SwapOrder.objects.filter(pk=self.swap.pk).values().get()
            values["uuid"] = uuid4()
            values["nonce"] += 1
            new_swap = SwapOrder(**values)
            capture_settlement_context(new_swap)
        with self.assertRaises(DatabaseError), atomic():
            SwapOrder.objects.bulk_create([new_swap])
        self.assertFalse(SwapOrder.objects.filter(pk=values["uuid"]).exists())
        with use_operator():
            new_swap.save()
        self.assertTrue(SwapOrder.objects.filter(pk=new_swap.pk).exists())
        self.assert_private_boundary()

    def test_membership_removed_after_verification_prevents_real_route_persistence(self):
        verify = AtomicSwapService.verify_signature

        def retire(service, *args):
            valid = verify(service, *args)
            self.assertTrue(valid)
            with use_operator():
                self.parties["seller"].account.user_profiles.remove(self.parties["seller"].profile)
            return valid

        with patch.object(AtomicSwapService, "verify_signature", retire):
            response = self.post_signature("buyer")
        self.assertEqual(response.status_code, 404, response.content)
        with use_operator():
            self.swap.refresh_from_db()
        self.assertFalse(self.swap.buyer_signature)
        self.event.assert_not_called()
        with use_operator():
            self.parties["seller"].account.user_profiles.add(self.parties["seller"].profile)
        self.assertEqual(self.post_signature("buyer").status_code, 200)

    def test_bound_caller_cannot_rebind_child_identity_or_use_wrong_route_identity(self):
        original = self.swap.settlement_context
        altered = deepcopy(original)
        altered["buyer"]["wallet_uuid"] = str(self.orders["seller"].wallet_id)
        for fields in (
            {"buyer_wallet_id": self.orders["seller"].wallet_id},
            {"buy_order_id": self.orders["seller"].pk},
            {"settlement_context": altered},
        ):
            with self.subTest(fields=sorted(fields)), self.assertRaises(IntegrityError), atomic():
                SwapOrder.objects.filter(pk=self.swap.pk).update(**fields)
        for name, wrong in (
            ("owner_account_uuid", str(self.parties["buyer"].account.pk)),
            ("wallet_uuid", str(self.orders["buyer"].wallet_id)),
            ("swap_uuid", str(uuid4())),
            ("settlement_digest", "0x" + "01" * 32),
        ):
            identity = {**self.identity, name: wrong}
            response = self.client.post(
                self.url + "sign/",
                {**identity, "signature": self.signature("buyer"), "signer_address": BUYER.address},
                format="json",
            )
            self.assertIn(response.status_code, (404, 409), response.content)
        with use_operator():
            self.swap.refresh_from_db()
        self.assertEqual(self.swap.settlement_context, original)
        self.assertFalse(self.swap.buyer_signature)
        self.event.assert_not_called()
        self.assertEqual(self.post_signature("buyer").status_code, 200)

    def test_operator_without_app_principal_keeps_the_original_both_visible_parent_path(self):
        with use_operator():
            reset_principal(current_alias())
            with connections[current_alias()].cursor() as cursor:
                cursor.execute(
                    "SELECT tokens_swap_has_current_party(s) FROM tokens_swaporder s WHERE uuid = %s", [self.swap.pk]
                )
                self.assertFalse(cursor.fetchone()[0])
            self.assertEqual(
                SwapOrder.objects.filter(pk=self.swap.pk).update(seller_signature=self.signature("seller")), 1
            )
        with use_operator():
            self.swap.refresh_from_db()
        self.assertEqual(self.swap.seller_signature, self.signature("seller"))

    def test_preflight_uses_the_schema_alias_when_the_ambient_principal_cannot_read_parents(self):
        self.no_principal_is_set()
        parent_id = self.orders["buyer"].pk
        owner_id = self.orders["buyer"].owner_account_id
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("ALTER TABLE tokens_transferorder DISABLE TRIGGER tokens_order_owner_identity_guard")
                try:
                    cursor.execute(
                        "UPDATE tokens_transferorder SET owner_account_id = %s WHERE uuid = %s",
                        [self.parties["seller"].account.pk, parent_id],
                    )
                finally:
                    cursor.execute("ALTER TABLE tokens_transferorder ENABLE TRIGGER tokens_order_owner_identity_guard")
            with self.assertRaisesMessage(RuntimeError, "buyer captured owner differs"):
                MIGRATION.refuse_parent_drift(apps, SimpleNamespace(connection=connections["operator"]))
            with use_operator():
                self.assertEqual(
                    TransferOrder.objects.get(pk=parent_id).owner_account_id, self.parties["seller"].account.pk
                )
        finally:
            with connections["default"].cursor() as cursor:
                cursor.execute("ALTER TABLE tokens_transferorder DISABLE TRIGGER tokens_order_owner_identity_guard")
                try:
                    cursor.execute(
                        "UPDATE tokens_transferorder SET owner_account_id = %s WHERE uuid = %s", [owner_id, parent_id]
                    )
                finally:
                    cursor.execute("ALTER TABLE tokens_transferorder ENABLE TRIGGER tokens_order_owner_identity_guard")
        MIGRATION.refuse_parent_drift(apps, SimpleNamespace(connection=connections["operator"]))
