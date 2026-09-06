from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from offerings.models import SubscriptionStatus
from offerings.services.subscription import accept, create_draft, submit
from offerings.tests.factories import (
    configure_operator,
    draft_subscription,
    eligible_subscriber,
    extra_wallet,
    open_offering,
)
from shared.tests.tenants import make_tenant
from users.constants import ACCOUNT_STATUS_ACTIVE
from users.exceptions import InvestorNotEligibleException
from users.models import (
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
    UserAccount,
)
from users.services.eligibility import (
    AMOUNT_BELOW_PRODUCT_VALUE_THRESHOLD,
    NO_LIVE_CLASSIFICATION,
    investor_eligibility,
)


class SubscriptionEligibilityScopeTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("twoaccounts")
        configure_operator()
        self.offering = open_offering(self.tenant)
        eligible_subscriber(self.tenant)

        self.unqualified = UserAccount.objects.create(
            account_number="ACCT-SECOND", account_status=ACCOUNT_STATUS_ACTIVE
        )
        self.unqualified.user_profiles.add(self.tenant.profile)
        self.second_wallet = extra_wallet(self.tenant, "7")
        self.second_wallet.user_account = self.unqualified
        self.second_wallet.save(update_fields=["user_account"])

    def _draft_on(self, account, wallet, quantity=10):
        return create_draft(self.offering, account, wallet, quantity, submitted_by=self.tenant.user)

    def test_the_users_first_account_qualifying_does_not_carry_the_second(self):
        self.assertTrue(investor_eligibility(self.tenant.user).is_eligible)

        subscription = self._draft_on(self.unqualified, self.second_wallet)
        with self.assertRaises(InvestorNotEligibleException) as raised:
            submit(subscription, submitted_by=self.tenant.user)

        self.assertEqual(raised.exception.reasons, (NO_LIVE_CLASSIFICATION,))
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.DRAFT)

    def test_the_qualified_account_of_the_same_user_still_subscribes(self):
        subscription = self._draft_on(self.tenant.account, self.tenant.wallet)
        submit(subscription, submitted_by=self.tenant.user)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.SUBMITTED)

    def test_the_predicate_is_called_with_the_subscriptions_account_and_amount(self):
        subscription = self._draft_on(self.tenant.account, self.tenant.wallet, quantity=12)
        with patch("offerings.services.subscription.require_subscription_eligibility") as predicate:
            submit(subscription, submitted_by=self.tenant.user)
        predicate.assert_called_once_with(self.tenant.account, self.offering.token.company, Decimal("30.00"))

    def test_the_predicate_is_called_again_with_the_same_account_at_accept(self):
        subscription = self._draft_on(self.tenant.account, self.tenant.wallet)
        submit(subscription, submitted_by=self.tenant.user)
        with patch("offerings.services.subscription.require_subscription_eligibility") as predicate:
            accept(subscription)
        predicate.assert_called_once_with(self.tenant.account, self.offering.token.company, Decimal("25.00"))

    def test_a_product_value_claim_below_the_threshold_cannot_subscribe(self):
        InvestorClassification.objects.filter(user_account=self.tenant.account).update(
            category=InvestorCategory.PRODUCT_VALUE
        )
        subscription = draft_subscription(self.tenant, quantity=10)
        with self.assertRaises(InvestorNotEligibleException) as raised:
            submit(subscription, submitted_by=self.tenant.user)
        self.assertEqual(raised.exception.reasons, (AMOUNT_BELOW_PRODUCT_VALUE_THRESHOLD,))

    def test_an_association_with_another_issuer_does_not_reach_this_offering(self):
        other = make_tenant("otherissuer")
        InvestorClassification.objects.filter(user_account=self.tenant.account).update(
            company=other.company,
            category=InvestorCategory.ASSOCIATED_PERSON,
            status=InvestorClassificationStatus.VERIFIED,
            expires_at=timezone.now() + timedelta(days=365),
        )
        subscription = draft_subscription(self.tenant)
        with self.assertRaises(InvestorNotEligibleException) as raised:
            submit(subscription, submitted_by=self.tenant.user)
        self.assertEqual(raised.exception.reasons, (NO_LIVE_CLASSIFICATION,))
