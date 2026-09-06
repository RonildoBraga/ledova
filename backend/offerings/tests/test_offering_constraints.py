from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from offerings.models import Offering, OfferingExemption, OfferingStatus
from shared.tests.tenants import make_tenant

LIVE = [OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW, OfferingStatus.APPROVED]
NOT_LIVE = [OfferingStatus.DRAFT, OfferingStatus.REJECTED, OfferingStatus.CLOSED, OfferingStatus.WITHDRAWN]


class OfferingConstraintTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("issuer")
        self.token = self.tenant.deployed_token
        self.opens_at = timezone.now() + timedelta(days=1)

    def _build(self, **overrides):
        fields = {
            "token": self.token,
            "exemption": OfferingExemption.PROFESSIONAL,
            "price_per_share": Decimal("1.00"),
            "minimum_shares": 10,
            "target_shares": 20,
            "cap_shares": 30,
            "opens_at": self.opens_at,
        }
        fields.update(overrides)
        return Offering(**fields)

    def _assert_one_live_refusal(self, message):
        named = connection.vendor == "postgresql"
        self.assertIn("offering_one_live_per_token" if named else "offerings_offering.token_id", message)

    def _refuses(self, **overrides):
        with self.assertRaises(IntegrityError) as raised:
            with transaction.atomic():
                self._build(**overrides).save()
        return str(raised.exception)

    def test_one_live_offering_per_token(self):
        for status in LIVE:
            with self.subTest(status=status):
                Offering.objects.exclude(pk=self.tenant.offering.pk).delete()
                Offering.objects.filter(pk=self.tenant.offering.pk).update(status=status)
                self._assert_one_live_refusal(self._refuses(status=status))

    def test_a_second_live_offering_on_another_token_is_allowed(self):
        Offering.objects.filter(pk=self.tenant.offering.pk).update(status=OfferingStatus.APPROVED)
        self._build(token=self.tenant.token, status=OfferingStatus.APPROVED).save()
        self.assertEqual(Offering.objects.live().count(), 2)

    def test_a_settled_offering_does_not_block_the_next_tranche(self):
        for status in NOT_LIVE:
            with self.subTest(status=status):
                Offering.objects.exclude(pk=self.tenant.offering.pk).delete()
                Offering.objects.filter(pk=self.tenant.offering.pk).update(status=status)
                self._build(status=OfferingStatus.APPROVED).save()

    def test_bounds_are_ordered_at_their_boundaries(self):
        self._build(minimum_shares=1, target_shares=1, cap_shares=1).save()
        self.assertIn("offering_bounds_ordered", self._refuses(minimum_shares=0, target_shares=0, cap_shares=0))
        self.assertIn("offering_bounds_ordered", self._refuses(minimum_shares=11, target_shares=10, cap_shares=30))
        self.assertIn("offering_bounds_ordered", self._refuses(minimum_shares=10, target_shares=20, cap_shares=19))

    def test_the_window_is_ordered_at_its_boundaries(self):
        self._build(closes_at=None).save()
        self._build(token=self.tenant.token, closes_at=self.opens_at + timedelta(seconds=1)).save()
        self.assertIn("offering_window_ordered", self._refuses(closes_at=self.opens_at))
        self.assertIn("offering_window_ordered", self._refuses(closes_at=self.opens_at - timedelta(seconds=1)))
