from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from shared.db import acting_for, atomic, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.settlement import save_swap_with_context
from shared.tests.tenants import make_tenant
from tokens.models import (
    OrderActionSubmission,
    OrderModificationLog,
    ShareToken,
    SigningChallenge,
    SwapOrder,
    TransferOrder,
)
from tokens.tests.order_action_fixtures import (
    BASE,
    OWNER,
    ActionFixtures,
    legacy_action_values,
)


class OrderActionRecoveryChecks(ActionFixtures):
    def test_malformed_or_oversized_quantities_are_field_errors_before_registration(self):
        for quantity in ("wrong", "9" * 5000, "9223372036854775808", 12, "01", "-1"):
            with self.subTest(quantity_kind=type(quantity).__name__, length=len(str(quantity))):
                response = self.message("modify", self.modify_body(new_quantity=quantity))
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("newQuantity", response.json())
        with use_operator():
            self.assertEqual(OrderActionSubmission.objects.count(), 0)
        self.assertEqual(self.message("modify", self.modify_body()).status_code, 200)

    def test_context_is_read_only_and_first_price_only_replacement_keeps_exact_quantities(self):
        exact = 9007199254740993
        with use_operator():
            TransferOrder.objects.filter(pk=self.order.pk).update(quantity=exact, min_quantity=exact - 1)
            initial_challenges = SigningChallenge.objects.count()
        context = self.context()
        self.assertEqual(context.status_code, 200, context.content)
        values = context.json()["currentValues"]
        self.assertEqual((values["quantity"], values["minQuantity"]), (str(exact), str(exact - 1)))
        self.assertTrue(values["canCancel"])
        self.assertTrue(values["canModify"])
        with use_operator():
            self.assertEqual(OrderActionSubmission.objects.count(), 0)
            self.assertEqual(SigningChallenge.objects.count(), initial_challenges)
        self.balance.get_token_balance.assert_not_called()
        body = self.modify_body(
            new_quantity=values["quantity"], new_min_quantity=values["minQuantity"], new_price_per_share="2.51"
        )
        response = self.message("modify", body)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["challenge"]["message"]["newQuantity"], str(exact))
        result = self.execute("modify", self.sign(response.json()))
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["intent"]["modifications"]["quantity"], str(exact))
        self.assertEqual(
            result.json()["result"]["changes"], [{"field": "price_per_share", "old": "2.50", "new": "2.51"}]
        )
        with use_operator():
            self.order.refresh_from_db()
        self.assertEqual((self.order.quantity, self.order.min_quantity), (exact, exact - 1))

    def test_cancel_lost_response_recovers_without_credentials_or_second_event(self):
        signed = self.signed()
        first = self.execute("cancel", signed)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["result"], {"kind": "cancel", "fromStatus": "open", "toStatus": "cancelled"})
        self.assertEqual(self.recover().json(), first.json())
        for credentials in ({}, {"digest": None, "signature": []}, {"digest": "old", "signature": "expired"}):
            replay = self.execute("cancel", {**self.identity(), **credentials})
            self.assertEqual(replay.status_code, 200, replay.content)
            self.assertEqual(replay.json(), first.json())
        self.assertEqual([event for event, _ in self.events], ["order_cancelled"])

    def test_modify_result_is_immutable_while_current_order_display_changes(self):
        first = self.execute("modify", self.signed("modify", self.modify_body()))
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["result"]["modificationCount"], 1)
        self.assertEqual(len(first.json()["result"]["changes"]), 3)
        with use_operator():
            self.assertEqual(OrderModificationLog.objects.filter(order=self.order).count(), 3)
        for status in ("cancelled", "executing", "failed"):
            with self.subTest(current_status=status):
                with use_operator():
                    TransferOrder.objects.filter(pk=self.order.pk).update(status=status)
                recovered = self.recover().json()
                self.assertEqual(recovered["result"], first.json()["result"])
                self.assertEqual(recovered["order"]["status"], status)
                self.assertEqual(self.execute("modify", self.identity()).json(), recovered)
        self.assertEqual([event for event, _ in self.events], ["order_modified"])

    def test_no_change_modification_records_its_increment_and_empty_changes(self):
        signed = self.signed(
            "modify", self.modify_body(new_quantity="10", new_min_quantity="0", new_price_per_share="2.50")
        )
        result = self.execute("modify", signed)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["result"], {"kind": "modify", "modificationCount": 1, "changes": []})
        self.assertEqual(self.recover().json(), result.json())

    def test_both_issuance_and_execution_provider_reads_are_outside_transactions(self):
        with use_operator():
            TransferOrder.objects.filter(pk=self.order.pk).update(order_type="sell")
        result = self.execute("modify", self.signed("modify", self.modify_body()))
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(self.provider_states, [False, False])
        self.assertEqual(result.json()["status"], "applied")

    def test_provider_failure_remains_pending_and_unspent(self):
        with use_operator():
            TransferOrder.objects.filter(pk=self.order.pk).update(order_type="sell")
        signed = self.signed("modify", self.modify_body())
        self.balance.get_token_balance.side_effect = RuntimeError("Synthetic provider outage")
        refused = self.execute("modify", signed)
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertNotIn("status", refused.json())
        self.assert_pending(signed)
        self.balance.get_token_balance.side_effect = self.provider_balance
        self.assertEqual(self.execute("modify", signed).status_code, 200)

    def test_same_id_changed_intent_is_an_ordinary_pending_conflict(self):
        signed = self.signed("modify", self.modify_body())
        conflict = self.message("modify", self.modify_body(new_price_per_share="4.00"))
        self.assertEqual(conflict.status_code, 409, conflict.content)
        self.assertEqual(conflict.json()["code"], "action_intent_conflict")
        self.assertNotIn("status", conflict.json())
        self.assert_pending(signed)
        self.assertEqual(self.execute("modify", signed).status_code, 200)

    def test_context_and_recovery_require_current_order_account_authorization(self):
        self.signed()
        with use_operator():
            other = make_tenant("action-foreign")
        self.assertEqual(self.context().status_code, 200)
        self.assertEqual(self.context(account_id=other.account.pk).status_code, 404)
        self.assertEqual(self.context(order=other.order, account_id=other.account.pk).status_code, 404)
        self.client.force_authenticate(other.user)
        self.assertEqual(self.recover().status_code, 404)
        self.assertEqual(self.execute("cancel", self.identity()).status_code, 404)
        self.client.force_authenticate(self.tenant.user)
        self.assertEqual(self.recover().status_code, 200)
        self.assertEqual(self.recover(action_id=uuid4()).status_code, 404)

    def test_a_lost_response_after_commit_recovers_without_a_second_mutation(self):
        signed = self.signed("modify", self.modify_body())
        with patch("tokens.views.trading_order.action_snapshot", side_effect=RuntimeError("synthetic lost response")):
            lost = self.execute("modify", signed)
        self.assertEqual(lost.status_code, 500)
        recovered = self.execute("modify", self.identity())
        self.assertEqual(recovered.status_code, 200, recovered.content)
        self.assertEqual(recovered.json()["result"]["modificationCount"], 1)
        self.assertEqual(self.recover().json(), recovered.json())
        with use_operator():
            self.assertEqual(OrderModificationLog.objects.filter(order=self.order).count(), 3)
        self.assertEqual(len(self.events), 1)

    def test_an_unexpected_post_mutation_failure_rolls_back_spend_changes_and_outcome(self):
        signed = self.signed("modify", self.modify_body())
        with patch(
            "tokens.models.order_action.OrderActionSubmission.save",
            side_effect=RuntimeError("synthetic journal write failure"),
        ):
            failed = self.execute("modify", signed)
        self.assertEqual(failed.status_code, 500)
        self.assert_pending(signed)
        with use_operator():
            self.order.refresh_from_db()
            self.assertEqual((self.order.quantity, self.order.modification_count), (10, 0))
            self.assertFalse(OrderModificationLog.objects.filter(order=self.order).exists())
        self.assertEqual(self.execute("modify", signed).status_code, 200)

    def test_two_challenges_for_one_action_converge_without_spending_the_unused_one(self):
        first = self.signed()
        second = self.signed()
        self.assertNotEqual(first["digest"], second["digest"])
        applied = self.execute("cancel", first)
        recovered = self.execute("cancel", second)
        self.assertEqual(applied.status_code, 200, applied.content)
        self.assertEqual(recovered.json(), applied.json())
        with use_operator():
            self.assertTrue(SigningChallenge.objects.get(digest=first["digest"]).is_consumed)
            self.assertFalse(SigningChallenge.objects.get(digest=second["digest"]).is_consumed)
        self.assertEqual(len(self.events), 1)

    def test_equal_deliberate_modifications_remain_distinct_actions(self):
        first = self.execute("modify", self.signed("modify", self.modify_body()))
        self.assertEqual(first.status_code, 200, first.content)
        self.action_id = uuid4()
        second = self.execute("modify", self.signed("modify", self.modify_body()))
        self.assertEqual(second.status_code, 200, second.content)
        self.assertNotEqual(first.json()["actionId"], second.json()["actionId"])
        self.assertEqual(first.json()["result"]["modificationCount"], 1)
        self.assertEqual(second.json()["result"], {"kind": "modify", "modificationCount": 2, "changes": []})
        self.assertEqual(len(self.events), 2)

    def test_current_domain_mismatch_leaves_pending_intent_unchanged_and_unspent(self):
        signed = self.signed()
        original = self.recover().json()["intent"]
        with override_settings(BLOCKCHAIN_CHAIN_ID=settings.BLOCKCHAIN_CHAIN_ID + 1):
            for response in (self.message(), self.execute("cancel", signed)):
                self.assertEqual(response.status_code, 409, response.content)
                self.assertEqual(response.json()["code"], "action_context_conflict")
                self.assertNotIn("status", response.json())
            self.assertEqual(self.recover().json()["intent"], original)
        self.assert_pending(signed)
        self.assertEqual(self.execute("cancel", signed).status_code, 200)

    def test_changed_or_unavailable_deployment_cannot_rebind_a_pending_action(self):
        signed = self.signed()
        token = self.tenant.deployed_token
        for changes in (
            {"contract_address": "0x" + "99" * 20},
            {"contract_address": "0x" + "00" * 20},
            {"status": "failed"},
        ):
            with self.subTest(changes=changes):
                with use_operator():
                    ShareToken.objects.filter(pk=token.pk).update(**changes)
                for response in (self.message(), self.execute("cancel", signed)):
                    self.assertEqual(response.status_code, 409, response.content)
                self.assert_pending(signed)
                with use_operator():
                    ShareToken.objects.filter(pk=token.pk).update(
                        contract_address=token.contract_address, status=token.status
                    )
        self.assertEqual(self.execute("cancel", signed).status_code, 200)

    def test_terminal_recovery_precedes_expired_credentials_and_new_deployment_checks(self):
        signed = self.signed()
        first = self.execute("cancel", signed)
        self.assertEqual(first.status_code, 200, first.content)
        with use_operator():
            ShareToken.objects.filter(pk=self.order.token_id).update(status="failed", contract_address="")
            deadline = SigningChallenge.objects.get(digest=signed["digest"]).expires_at
        with override_settings(BLOCKCHAIN_CHAIN_ID=settings.BLOCKCHAIN_CHAIN_ID + 1), patch(
            "tokens.models.signing_challenge.timezone.now", return_value=deadline + timedelta(days=1)
        ):
            for response in (
                self.execute("cancel", self.identity()),
                self.execute("cancel", signed),
                self.message(),
                self.recover(),
            ):
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["result"], first.json()["result"])
                self.assertEqual(response.json()["review"], first.json()["review"])
        fresh = self.message(body=self.identity(action_id=str(uuid4())))
        self.assertEqual(fresh.status_code, 409, fresh.content)

    def test_current_account_membership_is_required_before_pending_or_terminal_access(self):
        signed = self.signed()
        with use_operator():
            colleague = make_tenant("action-colleague")
            self.tenant.account.user_profiles.add(colleague.profile)
        self.client.force_authenticate(colleague.user)
        self.assertEqual(self.recover().status_code, 200)
        self.assertEqual(self.execute("cancel", signed).status_code, 200)
        self.assertEqual(self.journal().executed_by_id, colleague.user.pk)
        with use_operator():
            self.tenant.account.user_profiles.remove(colleague.profile)
        for response in (self.context(), self.message(), self.execute("cancel", self.identity()), self.recover()):
            self.assertEqual(response.status_code, 404, response.content)
        self.client.force_authenticate(self.tenant.user)
        self.assertEqual(self.recover().status_code, 200)

    def test_removed_membership_cannot_spend_or_poison_a_pending_action(self):
        signed = self.signed()
        with use_operator():
            self.tenant.account.user_profiles.remove(self.tenant.profile)
        for response in (self.execute("cancel", signed), self.message(), self.recover()):
            self.assertEqual(response.status_code, 404, response.content)
        self.assert_pending(signed)
        with use_operator():
            self.tenant.account.user_profiles.add(self.tenant.profile)
        self.assertEqual(self.execute("cancel", signed).status_code, 200)

    def test_modified_signature_fields_and_domain_are_refused_without_spending(self):
        response = self.message("modify", self.modify_body())
        self.assertEqual(response.status_code, 200, response.content)
        snapshot = response.json()
        changes = {
            "actionId": str(uuid4()),
            "ownerAccountUuid": str(uuid4()),
            "walletUuid": str(uuid4()),
            "tokenUuid": str(uuid4()),
            "orderUuid": str(uuid4()),
            "protocolVersion": "2",
            "newQuantity": "13",
            "newMinQuantity": "2",
            "newPricePerShare": "4.00",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                altered = deepcopy(snapshot)
                altered["challenge"]["message"][field] = value
                refused = self.execute("modify", self.sign(altered))
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assert_pending(self.sign(snapshot))
        altered = deepcopy(snapshot)
        altered["challenge"]["domain"]["verifyingContract"] = "0x" + "99" * 20
        self.assertEqual(self.execute("modify", self.sign(altered)).status_code, 403)
        self.assertEqual(self.execute("modify", self.sign(snapshot)).status_code, 200)

    def test_a_pending_swap_is_a_recorded_refusal_only_after_validated_execution(self):
        signed = self.signed("modify", self.modify_body())
        with use_operator():
            swap = save_swap_with_context(
                sell_order=self.tenant.order,
                buy_order=self.order,
                share_token=self.order.token,
                payment_asset=self.order.payment_asset,
                seller_address=self.tenant.wallet.address,
                buyer_address=self.wallet.address,
                share_amount=1,
                payment_amount=250,
                nonce=999991,
                order_hash="0x" + "bd" * 32,
                expires_at=timezone.now() + timedelta(minutes=5),
            )
        first = self.execute("modify", signed)
        self.assertEqual(first.status_code, 409, first.content)
        self.assertEqual(first.json()["status"], "refused")
        self.assertEqual(first.json()["refusal"]["code"], "order_modification_conflict")
        self.assertEqual(first.json()["refusal"]["httpStatus"], 409)
        with use_operator():
            SwapOrder.objects.filter(pk=swap.pk).update(status="failed")
        recovered = self.execute("modify", self.identity())
        self.assertEqual(recovered.status_code, 409, recovered.content)
        self.assertEqual(recovered.json()["refusal"], first.json()["refusal"])
        self.assertEqual(self.recover().status_code, 200)
        self.action_id = uuid4()
        self.assertEqual(self.execute("modify", self.signed("modify", self.modify_body())).status_code, 200)

    def test_a_caller_transaction_is_refused_before_registration_or_spending(self):
        with atomic():
            response = self.message()
        self.assertEqual(response.status_code, 503, response.content)
        with use_operator():
            self.assertFalse(OrderActionSubmission.objects.exists())
        signed = self.signed()
        with atomic():
            response = self.execute("cancel", signed)
        self.assertEqual(response.status_code, 503, response.content)
        self.assert_pending(signed)
        self.assertEqual(self.execute("cancel", signed).status_code, 200)

    def test_unlinked_legacy_credentials_require_refresh_without_consuming_the_old_record(self):
        for purpose in ("cancel", "modify"):
            self.action_id = uuid4()
            message_body = self.identity() if purpose == "cancel" else self.modify_body()
            issued = self.message(purpose, message_body)
            self.assertEqual(issued.status_code, 200, issued.content)
            values, signature = legacy_action_values(self.order, OWNER, purpose, 7231 + (purpose == "modify"))
            with use_operator():
                old = SigningChallenge.objects.create(**values)
            response = self.execute(purpose, {**self.identity(), "digest": old.digest, "signature": signature})
            self.assertEqual(response.status_code, 400, response.content)
            self.assertEqual(response.json()["code"], "action_refresh_required")
            with use_operator():
                old.refresh_from_db()
                self.assertIsNone(old.action_id)
                self.assertIsNone(old.consumed_at)
                self.assertEqual(old.payload, values["payload"])
            self.assertEqual(self.execute(purpose, self.sign(issued.json())).status_code, 200)
            with use_operator():
                TransferOrder.objects.filter(pk=self.order.pk).update(status="open")

    def test_uuid_path_spelling_does_not_change_the_recorded_order_identity(self):
        normal = self.message()
        self.assertEqual(normal.status_code, 200, normal.content)
        renewed = self.client.post(
            f"{BASE}{str(self.order.pk).upper()}/cancel/message/", self.identity(), format="json"
        )
        self.assertEqual(renewed.status_code, 200, renewed.content)
        self.assertEqual(renewed.json()["actionId"], normal.json()["actionId"])
        self.assertEqual(renewed.json()["orderUuid"], str(self.order.pk))
        missing = self.client.post(f"{BASE}not-a-uuid/cancel/", self.identity(), format="json")
        self.assertEqual(missing.status_code, 404, missing.content)
        self.assertEqual(self.execute("cancel", self.sign(renewed.json())).status_code, 200)


class OrderActionRecoveryTest(OrderActionRecoveryChecks, APITransactionTestCase):
    pass


class ScopedOrderActionRecoveryTest(RunsOnTheScopedConnection, OrderActionRecoveryChecks, APITransactionTestCase):
    def test_a_hidden_token_does_not_hide_the_owned_terminal_action_or_its_recorded_display(self):
        with use_operator():
            other = make_tenant("hidden-action-token")
            self.order = TransferOrder.objects.create(
                token=other.deployed_token,
                payment_asset=self.tenant.refs.stablecoin,
                wallet=self.wallet,
                owner_account=self.tenant.account,
                wallet_address=self.wallet.address,
                order_type="buy",
                quantity=10,
                min_quantity=0,
                price_per_share="2.50",
            )
        signed = self.signed()
        first = self.execute("cancel", signed)
        self.assertEqual(first.status_code, 200, first.content)
        with acting_for(self.tenant.user.pk):
            self.assertTrue(ShareToken.objects.filter(pk=self.order.token_id).exists())
        with use_operator():
            ShareToken.objects.filter(pk=self.order.token_id).update(status="paused")
        with acting_for(self.tenant.user.pk):
            self.assertFalse(ShareToken.objects.filter(pk=self.order.token_id).exists())
            self.assertTrue(TransferOrder.objects.visible_to_user(self.tenant.user).filter(pk=self.order.pk).exists())
        recovered = self.recover()
        self.assertEqual(recovered.status_code, 200, recovered.content)
        self.assertEqual(recovered.json()["order"]["tokenName"], first.json()["order"]["tokenName"])
        self.assertEqual(recovered.json()["order"]["tokenSymbol"], first.json()["order"]["tokenSymbol"])
        self.assertEqual(recovered.json()["result"], first.json()["result"])
        self.assertEqual(self.execute("cancel", self.identity()).status_code, 200)
        self.assertEqual(self.context().status_code, 409)
        self.assertEqual(len(self.events), 1)
