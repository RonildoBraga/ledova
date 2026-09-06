from decimal import Decimal
from unittest.mock import patch

from django import forms
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from web3 import Web3

from offerings.admin.subscription import ACTIONS
from offerings.models import (
    Offering,
    SettlementRail,
    Subscription,
    SubscriptionStatus,
)
from offerings.services.subscription import BATCH_ABOVE_HEADROOM, REFUND_NOT_POSITIVE
from offerings.tests.factories import (
    configure_operator,
    draft_subscription,
    eligible_subscriber,
    extra_wallet,
    open_offering,
    paid_subscription,
)
from shared.tests.tenants import make_tenant
from tokens.models import RequestStatus, ShareIssuanceRequest
from users.models import InvestorClassification
from whitelist.models import WhitelistEntry

User = get_user_model()
CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"
DEFER = "offerings.tasks.subscription.allot_subscription_task.defer"
SUPPLY = "tokens.services.share_token_service.ShareTokenService.share_supply"
SIGNER = "0x" + "e" * 40
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class SubscriptionAdminTestCase(TestCase):
    def setUp(self):
        chain = patch(CHAIN_CLIENT).start().return_value
        chain.is_valid_address.return_value = True
        chain.to_checksum_address.side_effect = Web3.to_checksum_address
        chain.get_address_from_private_key.return_value = SIGNER
        self.defer = patch(DEFER).start()
        self.addCleanup(patch.stopall)

        self.tenant = make_tenant("adminsub")
        self.stablecoin = self.tenant.refs.stablecoin
        configure_operator(stablecoin=self.stablecoin)
        self.offering = open_offering(self.tenant, stablecoin=self.stablecoin, target_shares=200, cap_shares=500)
        eligible_subscriber(self.tenant)
        self.operator = User.objects.create_superuser(email="ops@example.test", password="pw-12345678")
        self.client.force_login(self.operator)

    def _url(self, subscription, action):
        return reverse("admin:offerings_subscription_action", args=[subscription.uuid, action])

    def _change_url(self, subscription):
        return reverse("admin:offerings_subscription_change", args=[subscription.pk])

    def _messages(self, response):
        return [str(message) for message in response.wsgi_request._messages]

    def _submitted(self, quantity=10, wallet=None):
        subscription = draft_subscription(self.tenant, quantity=quantity, wallet=wallet)
        Subscription.objects.filter(pk=subscription.pk).update(status=SubscriptionStatus.SUBMITTED)
        subscription.refresh_from_db()
        return subscription

    def _allot(self, subscriptions):
        return self.client.post(
            reverse("admin:offerings_subscription_changelist"),
            {
                "action": "allot_selected",
                "_selected_action": [str(row.pk) for row in subscriptions],
            },
            follow=True,
        )


class SubscriptionAdminTest(SubscriptionAdminTestCase):
    def test_the_add_form_is_closed_and_every_field_is_read_only(self):
        subscription = draft_subscription(self.tenant)
        add = self.client.get(reverse("admin:offerings_subscription_add"))
        self.assertEqual(add.status_code, 403)
        change = self.client.get(self._change_url(subscription))
        self.assertEqual(change.status_code, 200)
        self.assertEqual(dict(change.context["adminform"].form.fields), {})

    def test_accept_and_issue_walks_the_row_to_awaiting_payment_in_one_click(self):
        subscription = self._submitted()
        confirm = self.client.get(self._url(subscription, "accept"))
        self.assertEqual(confirm.status_code, 200)

        response = self.client.post(
            self._url(subscription, "accept"), {"settlement_rail": SettlementRail.BANK_TRANSFER}, follow=True
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.AWAITING_PAYMENT)
        self.assertTrue(subscription.reference.startswith("PAY"))
        self.assertIn("Accepted; the payment instruction is issued.", self._messages(response))

    def test_accept_surfaces_a_lapsed_classification_as_an_error_not_a_500(self):
        subscription = self._submitted()
        InvestorClassification.objects.filter(user_account=self.tenant.account).update(expires_at=timezone.now())

        response = self.client.post(
            self._url(subscription, "accept"), {"settlement_rail": SettlementRail.BANK_TRANSFER}, follow=True
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.SUBMITTED)
        self.assertIn("not eligible to invest", self._messages(response)[0])

    def test_a_stablecoin_instruction_without_a_deployment_is_an_error_message(self):
        from assets.models import AssetChainDeployment

        AssetChainDeployment.objects.filter(asset=self.stablecoin, chain="base").update(is_active=False)
        subscription = self._submitted()
        response = self.client.post(
            self._url(subscription, "accept"),
            {"settlement_rail": SettlementRail.STABLECOIN, "settlement_asset": self.stablecoin.pk},
            follow=True,
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ACCEPTED)
        self.assertIn("no active deployment", self._messages(response)[0])

    def test_confirm_payment_records_the_money_and_the_operator_who_saw_it(self):
        subscription = self._submitted()
        self.client.post(self._url(subscription, "accept"), {"settlement_rail": SettlementRail.BANK_TRANSFER})
        subscription.refresh_from_db()

        response = self.client.post(
            self._url(subscription, "confirm-payment"),
            {
                "amount_received": "25.00",
                "payment_received_on": "2026-09-01",
                "payment_reference_seen": f"transfer {subscription.reference.lower()}",
                "payment_notes": "Seen on the statement",
            },
            follow=True,
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertEqual(subscription.amount_received, Decimal("25.00"))
        self.assertEqual(subscription.payment_confirmed_by, self.operator)
        self.assertIn("Payment confirmed.", self._messages(response))

    def test_reject_is_refused_while_money_is_recorded_and_allowed_after_a_refund(self):
        subscription = paid_subscription(self.tenant)
        refused = self.client.post(self._url(subscription, "reject"), {"reason": "No longer proceeding"}, follow=True)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertIn("Record a refund before rejecting", self._messages(refused)[0])

        self.client.post(
            self._url(subscription, "refund"),
            {"refund_amount": "25.00", "refund_reference": "RTGS-9", "payment_notes": "Returned"},
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REFUNDED)

        self.client.post(self._url(subscription, "reject"), {"reason": "Unwound"}, follow=True)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REJECTED)

    def test_retry_defers_the_task_again(self):
        subscription = paid_subscription(self.tenant)
        with patch(SUPPLY, return_value=(1000, 0)):
            self._allot([subscription])
        subscription.refresh_from_db()
        self.defer.reset_mock()

        response = self.client.post(self._url(subscription, "retry"), {}, follow=True)
        self.assertEqual(self.defer.call_count, 1)
        self.assertIn("Allotment retried; the task is running in the background.", self._messages(response))

    def test_the_bulk_action_allots_a_batch_inside_the_headroom(self):
        rows = [paid_subscription(self.tenant, quantity=40, wallet=extra_wallet(self.tenant, n)) for n in "12"]
        with patch(SUPPLY, return_value=(1000, 0)):
            response = self._allot(rows)

        self.assertIn("Allotted 2 subscription(s).", self._messages(response))
        self.assertEqual(ShareIssuanceRequest.objects.count(), 2)
        self.assertEqual(self.defer.call_count, 2)

    def test_the_bulk_action_refuses_the_whole_batch_over_the_cap_and_allots_nothing(self):
        rows = [paid_subscription(self.tenant, quantity=40, wallet=extra_wallet(self.tenant, n)) for n in "123"]
        Offering.objects.filter(pk=self.offering.pk).update(minimum_shares=1, target_shares=100, cap_shares=100)

        with patch(SUPPLY, return_value=(1000, 0)):
            response = self._allot(rows)

        self.assertIn(
            BATCH_ABOVE_HEADROOM.format(
                total=120, symbol=self.offering.token.symbol, room=100, cap_room=100, chain_room=1000
            ),
            self._messages(response),
        )
        self.assertFalse(ShareIssuanceRequest.objects.exists())
        self.assertEqual(self.defer.call_count, 0)

    def test_the_bulk_scale_back_action_cuts_the_offering_pro_rata(self):
        rows = [paid_subscription(self.tenant, quantity=60, wallet=extra_wallet(self.tenant, n)) for n in "12"]
        Offering.objects.filter(pk=self.offering.pk).update(minimum_shares=1, target_shares=60, cap_shares=60)

        response = self.client.post(
            reverse("admin:offerings_subscription_changelist"),
            {"action": "scale_back_selected", "_selected_action": [str(row.pk) for row in rows]},
            follow=True,
        )

        for row in rows:
            row.refresh_from_db()
        self.assertEqual([row.allotted_quantity for row in rows], [30, 30])
        self.assertIn("2 subscription(s) scaled", self._messages(response)[0])

    def test_the_bulk_whitelist_action_calls_the_existing_service(self):
        subscription = paid_subscription(self.tenant)
        entry = WhitelistEntry.objects.create(wallet=self.tenant.wallet)

        with patch("whitelist.services.WhitelistService") as service:
            service.return_value.ensure_whitelisted.return_value = {
                "added": 1,
                "synced": 0,
                "skipped": 0,
                "errors": [],
            }
            response = self.client.post(
                reverse("admin:offerings_subscription_changelist"),
                {"action": "whitelist_wallets", "_selected_action": [str(subscription.pk)]},
                follow=True,
            )

        service.return_value.ensure_whitelisted.assert_called_once()
        self.assertEqual(list(service.return_value.ensure_whitelisted.call_args.args[0]), [entry])
        self.assertIn("Whitelisted 1 and synced 0 address(es).", self._messages(response))

    def test_the_bulk_whitelist_action_names_the_wallets_with_no_entry(self):
        subscription = paid_subscription(self.tenant)
        response = self.client.post(
            reverse("admin:offerings_subscription_changelist"),
            {"action": "whitelist_wallets", "_selected_action": [str(subscription.pk)]},
            follow=True,
        )
        self.assertIn("1 wallet(s) have no whitelist entry; add them first.", self._messages(response))

    def test_the_changelist_finds_a_row_by_a_mangled_bank_narrative(self):
        subscription = self._submitted()
        self.client.post(self._url(subscription, "accept"), {"settlement_rail": SettlementRail.BANK_TRANSFER})
        subscription.refresh_from_db()
        mangled = f"  {subscription.reference[:3].lower()}/{subscription.reference[3:].lower()} "

        response = self.client.get(reverse("admin:offerings_subscription_changelist"), {"q": mangled})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row.pk for row in response.context["cl"].result_list], [subscription.pk])

    def test_an_allotted_row_offers_no_further_action(self):
        subscription = paid_subscription(self.tenant)
        Subscription.objects.filter(pk=subscription.pk).update(status=SubscriptionStatus.ALLOTTED)
        subscription.refresh_from_db()
        response = self.client.get(self._change_url(subscription))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self._url(subscription, "reject"), response.content.decode())

    def test_the_allot_action_refuses_a_row_that_already_has_a_request(self):
        subscription = paid_subscription(self.tenant)
        with patch(SUPPLY, return_value=(1000, 0)):
            self._allot([subscription])
            subscription.refresh_from_db()
            self.assertEqual(subscription.issuance_request.status, RequestStatus.APPROVED)
            response = self._allot([subscription])

        self.assertEqual(ShareIssuanceRequest.objects.count(), 1)
        self.assertIn("cannot be allotted twice", self._messages(response)[0])


@override_settings(STORAGES=TEST_STORAGES)
class SubscriptionAdminMoneyTest(SubscriptionAdminTestCase):
    def _awaiting(self, quantity=10, wallet=None):
        subscription = self._submitted(quantity=quantity, wallet=wallet)
        self.client.post(self._url(subscription, "accept"), {"settlement_rail": SettlementRail.BANK_TRANSFER})
        subscription.refresh_from_db()
        return subscription

    def _confirm(self, subscription, amount, received_on="2026-09-01", line=""):
        return self.client.post(
            self._url(subscription, "confirm-payment"),
            {
                "amount_received": amount,
                "payment_received_on": received_on,
                "payment_reference_seen": line,
            },
            follow=True,
        )

    def _warnings(self, response):
        return [str(message) for message in response.wsgi_request._messages if message.level_tag == "warning"]

    def _refund(self, subscription, amount, reference=""):
        return self.client.post(
            self._url(subscription, "refund"),
            {"refund_amount": amount, "refund_reference": reference, "payment_notes": ""},
            follow=True,
        )

    def test_a_part_refunded_row_keeps_the_refund_button_until_every_cent_is_back(self):
        subscription = self._awaiting()
        self._confirm(subscription, "25.00")
        self._refund(subscription, "1.00", "RTGS-PART")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REFUNDED)
        self.assertEqual(subscription.money_held, Decimal("24.00"))

        change = self.client.get(self._change_url(subscription)).content.decode()
        self.assertIn(self._url(subscription, "refund"), change)

        refused = self.client.post(self._url(subscription, "reject"), {"reason": "Close it"}, follow=True)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REFUNDED)
        self.assertIn("Record a refund before rejecting", self._messages(refused)[0])

        response = self._refund(subscription, "24.00", "RTGS-REST")
        subscription.refresh_from_db()
        self.assertEqual(self._messages(response)[-1], "Refund recorded.")
        self.assertEqual(subscription.refund_amount, Decimal("25.00"))
        self.assertEqual(subscription.money_held, Decimal("0.00"))

        self.client.post(self._url(subscription, "reject"), {"reason": "Unwound"}, follow=True)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REJECTED)

    def test_the_refund_form_will_not_take_a_zero(self):
        subscription = paid_subscription(self.tenant)
        response = self.client.post(
            self._url(subscription, "refund"), {"refund_amount": "0.00", "refund_reference": "NOTHING"}
        )
        subscription.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIn("refund_amount", response.context["form"].errors)
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertIsNone(subscription.refunded_at)

    def test_a_zero_refund_that_dodges_the_form_is_still_refused_by_the_service(self):
        subscription = paid_subscription(self.tenant)
        loose = {**ACTIONS["refund"], "form": ZeroTolerantRefundForm}
        with patch.dict("offerings.admin.subscription.ACTIONS", {"refund": loose}):
            response = self.client.post(self._url(subscription, "refund"), {"refund_amount": "0.00"}, follow=True)
        subscription.refresh_from_db()
        self.assertEqual(self._messages(response), [REFUND_NOT_POSITIVE])
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)

        rejected = self.client.post(self._url(subscription, "reject"), {"reason": "gone"}, follow=True)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertIn("Record a refund before rejecting", self._messages(rejected)[0])

    def test_every_money_action_leaves_an_entry_in_the_admin_history(self):
        subscription = self._awaiting()
        self._confirm(subscription, "25.00")
        self.client.post(
            self._url(subscription, "refund"), {"refund_amount": "25.00", "refund_reference": "RTGS-9"}, follow=True
        )
        self.client.post(self._url(subscription, "reject"), {"reason": "Unwound"}, follow=True)

        entries = [entry.change_message for entry in LogEntry.objects.order_by("action_time")]
        self.assertEqual(len(entries), 4)
        self.assertIn(f"Accepted and issued payment instruction {subscription.reference}", entries[0])
        self.assertIn("Recorded 25.00 received on 2026-09-01", entries[1])
        self.assertIn("Recorded a refund of 25.00", entries[2])
        self.assertIn("Rejected the subscription: Unwound", entries[3])
        self.assertEqual({entry.user_id for entry in LogEntry.objects.all()}, {self.operator.pk})

    def test_a_restatement_downwards_warns_the_operator_and_records_the_old_figure(self):
        subscription = self._awaiting()
        self._confirm(subscription, "25.00")
        response = self._confirm(subscription, "1.00", received_on="2026-09-02")
        subscription.refresh_from_db()

        self.assertEqual(subscription.amount_received, Decimal("1.00"))
        self.assertIn("restated down from 25.00 to 1.00", self._warnings(response)[0])
        self.assertIn("Recorded 25.00 received", LogEntry.objects.order_by("action_time")[1].change_message)

    def test_a_statement_line_recorded_twice_warns_rather_than_passing_silently(self):
        first = self._awaiting()
        second = self._awaiting(wallet=extra_wallet(self.tenant, "8"))
        line = "CBA 04/09 DEPOSIT 000123456"

        self.assertEqual(self._warnings(self._confirm(first, "25.00", line=line)), [])
        warned = self._warnings(self._confirm(second, "25.00", line=line))

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.status, SubscriptionStatus.PAID)
        self.assertIn(f"already recorded against {first.reference}", warned[0])

    def test_a_bulk_allotment_and_a_scale_back_both_reach_the_admin_history(self):
        rows = [paid_subscription(self.tenant, quantity=60, wallet=extra_wallet(self.tenant, n)) for n in "12"]
        Offering.objects.filter(pk=self.offering.pk).update(minimum_shares=1, target_shares=60, cap_shares=60)
        self.client.post(
            reverse("admin:offerings_subscription_changelist"),
            {"action": "scale_back_selected", "_selected_action": [str(row.pk) for row in rows]},
            follow=True,
        )
        with patch(SUPPLY, return_value=(1000, 0)):
            self._allot(rows)

        entries = [entry.change_message for entry in LogEntry.objects.order_by("action_time")]
        self.assertEqual(len([entry for entry in entries if entry.startswith("Scaled back to 30 share(s)")]), 2)
        self.assertEqual(len([entry for entry in entries if entry.startswith("Allotted 30 share(s)")]), 2)

    def test_an_allotted_row_can_still_return_the_residual_a_scale_back_stranded(self):
        subscription = paid_subscription(self.tenant, quantity=10)
        Offering.objects.filter(pk=self.offering.pk).update(minimum_shares=1, target_shares=5, cap_shares=5)
        self.client.post(
            reverse("admin:offerings_subscription_changelist"),
            {"action": "scale_back_selected", "_selected_action": [str(subscription.pk)]},
            follow=True,
        )
        with patch(SUPPLY, return_value=(1000, 0)):
            self._allot([subscription])
        subscription.refresh_from_db()
        ShareIssuanceRequest.objects.filter(pk=subscription.issuance_request_id).update(status=RequestStatus.EXECUTED)
        subscription.refresh_from_db()
        subscription.mark_allotted()

        change = self.client.get(self._change_url(subscription))
        self.assertIn(self._url(subscription, "refund"), change.content.decode())

        response = self.client.post(
            self._url(subscription, "refund"),
            {"refund_amount": "12.50", "refund_reference": "RTGS-RESIDUAL"},
            follow=True,
        )
        subscription.refresh_from_db()
        self.assertEqual(self._messages(response)[-1], "Refund recorded.")
        self.assertEqual(subscription.status, SubscriptionStatus.ALLOTTED)
        self.assertEqual(subscription.refund_amount, Decimal("12.50"))


class ZeroTolerantRefundForm(forms.Form):

    refund_amount = forms.DecimalField(max_digits=18, decimal_places=2)
    refund_reference = forms.CharField(max_length=140, required=False)
    payment_notes = forms.CharField(required=False)
