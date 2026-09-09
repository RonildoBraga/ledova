from unittest import skipUnless

from django.conf import settings
from django.db import connection, transaction
from django.db.utils import ProgrammingError
from django.test import TestCase

from offerings.exceptions import SubscriptionRefusedException
from offerings.models import Subscription
from offerings.services.subscription import withdraw
from shared.db.principal import PRINCIPAL_SETTING
from shared.tests.tenants import make_tenant, open_to_investors
from tokens.models import CapitalIncreaseRequest, RequestStatus, ShareIssuanceRequest


@skipUnless(connection.vendor == "postgresql", "PostgreSQL request policies")
class ReviewRequestPolicyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.one = make_tenant("request-policy-one")
        cls.two = make_tenant("request-policy-two")
        cls.requests = []
        for tenant in (cls.one, cls.two):
            issuance = ShareIssuanceRequest.objects.create(
                token=tenant.deployed_token,
                recipient_address=tenant.wallet.address,
                amount=1,
                reason="Synthetic issuance",
            )
            cls.requests.append((tenant.capital_increase, issuance))

    def as_app(self, user):
        self.addCleanup(self.restore_role)
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
            cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(user.pk) if user else ""])

    def restore_role(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])

    def test_unfiltered_reads_are_limited_to_the_principals_company(self):
        self.as_app(self.one.user)
        for model, own in zip((CapitalIncreaseRequest, ShareIssuanceRequest), self.requests[0]):
            with self.subTest(model=model.__name__):
                self.assertEqual(list(model.objects.all()), [own])

    def test_a_missing_principal_sees_no_requests(self):
        self.as_app(None)
        for model in (CapitalIncreaseRequest, ShareIssuanceRequest):
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.exists())

    def test_own_rows_can_be_locked_and_edited_but_foreign_rows_cannot(self):
        self.as_app(self.one.user)
        for own, foreign, field in zip(self.requests[0], self.requests[1], ("purpose", "reason")):
            with self.subTest(model=type(own).__name__):
                model = type(own)
                self.assertEqual(model.objects.select_for_update().get(pk=own.pk), own)
                self.assertFalse(model.objects.select_for_update().filter(pk=foreign.pk).exists())
                self.assertEqual(model.objects.filter(pk=own.pk).update(**{field: "Updated"}), 1)
                self.assertEqual(model.objects.filter(pk=foreign.pk).update(**{field: "Forged"}), 0)

    def test_a_foreign_request_cannot_be_deleted(self):
        self.as_app(self.one.user)
        for foreign in self.requests[1]:
            with self.subTest(model=type(foreign).__name__):
                self.assertEqual(type(foreign).objects.filter(pk=foreign.pk).delete()[0], 0)

    def create_requests(self, tenant):
        return (
            (
                CapitalIncreaseRequest,
                dict(token=tenant.deployed_token, additional_shares=1, new_authorized_total=1001, purpose="Synthetic"),
            ),
            (
                ShareIssuanceRequest,
                dict(
                    token=tenant.deployed_token, recipient_address=tenant.wallet.address, amount=1, reason="Synthetic"
                ),
            ),
        )

    def test_inserts_for_the_owning_company_remain_allowed(self):
        self.as_app(self.one.user)
        for model, fields in self.create_requests(self.one):
            with self.subTest(model=model.__name__):
                self.assertEqual(model.objects.create(**fields).company_id, self.one.company.pk)

    def test_inserts_for_a_foreign_company_are_refused_by_the_policy(self):
        self.as_app(self.one.user)
        for model, fields in self.create_requests(self.two):
            with self.subTest(model=model.__name__):
                with self.assertRaises(ProgrammingError) as refused:
                    with transaction.atomic():
                        model.objects.create(**fields)
                self.assertIn("row-level security", str(refused.exception))

    def link_another_issuers_request(self):
        request = self.requests[1][1]
        open_to_investors(self.two)
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.EXECUTING)
        self.cross_subscription = Subscription.objects.create(
            offering=self.two.offering,
            user_account=self.one.account,
            wallet=self.one.wallet,
            submitted_by=self.one.user,
            quantity=10,
            price_per_share=self.two.offering.price_per_share,
            amount_due=25,
            issuance_request=request,
        )
        return request

    def test_a_subscriber_can_read_only_the_linked_request_of_another_issuer(self):
        linked = self.link_another_issuers_request()
        unrelated = ShareIssuanceRequest.objects.create(
            token=self.two.deployed_token,
            recipient_address=self.two.wallet.address,
            amount=1,
            reason="An unrelated issuance",
        )
        self.as_app(self.one.user)

        self.assertEqual(ShareIssuanceRequest.objects.get(pk=linked.pk), linked)
        self.assertFalse(ShareIssuanceRequest.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(
            Subscription.objects.with_relations().get(pk=self.cross_subscription.pk).issuance_request, linked
        )

    def test_reading_a_subscriptions_issuance_request_does_not_allow_editing_or_deleting_it(self):
        linked = self.link_another_issuers_request()
        self.as_app(self.one.user)

        self.assertEqual(ShareIssuanceRequest.objects.select_for_update().get(pk=linked.pk), linked)
        with self.assertRaises(ProgrammingError) as refused:
            with transaction.atomic():
                ShareIssuanceRequest.objects.filter(pk=linked.pk).update(status=RequestStatus.REJECTED)
        self.assertIn("row-level security", str(refused.exception))
        self.assertEqual(ShareIssuanceRequest.objects.filter(pk=linked.pk).delete()[0], 0)

    def test_withdrawal_after_an_issuance_is_claimed_still_returns_the_business_refusal(self):
        self.link_another_issuers_request()
        original_status = self.cross_subscription.status
        self.as_app(self.one.user)

        with self.assertRaises(SubscriptionRefusedException) as refused:
            withdraw(self.cross_subscription)
        self.assertIn("Withdrawing it", str(refused.exception.detail))
        self.assertIn("executing", str(refused.exception.detail))
        self.cross_subscription.refresh_from_db()
        self.assertEqual(self.cross_subscription.status, original_status)
