from django.db import transaction
from django.test import TransactionTestCase

from feature_flags.models import FeatureFlag
from shared.services import act_under_row_lock
from tokens.exceptions import OrderCancellationException

NAME = "row_lock_probe"


class ARefusalReturnedKeepsWhatTheBlockWroteTest(TransactionTestCase):

    def setUp(self):
        self.flag, _ = FeatureFlag.objects.update_or_create(name=NAME, defaults={"enabled": False})

    def flags(self):
        return sorted(FeatureFlag.objects.filter(name__startswith=NAME).values_list("name", flat=True))

    def test_a_refusal_returned_from_inside_keeps_the_write_beside_it(self):
        def act(row):
            FeatureFlag.objects.create(name=f"{NAME}_written", enabled=False)
            return row, OrderCancellationException("the rule refused this")

        with self.assertRaises(OrderCancellationException):
            act_under_row_lock(FeatureFlag.objects.all(), self.flag.pk, act)

        self.assertEqual(self.flags(), [NAME, f"{NAME}_written"])

    def test_a_refusal_raised_from_inside_takes_the_write_with_it(self):
        def act(row):
            FeatureFlag.objects.create(name=f"{NAME}_written", enabled=False)
            raise OrderCancellationException("raised rather than returned")

        with self.assertRaises(OrderCancellationException):
            act_under_row_lock(FeatureFlag.objects.all(), self.flag.pk, act)

        self.assertEqual(self.flags(), [NAME])

    def test_a_value_returned_with_no_refusal_is_handed_back(self):
        def act(row):
            FeatureFlag.objects.create(name=f"{NAME}_written", enabled=False)
            return "done", None

        self.assertEqual(act_under_row_lock(FeatureFlag.objects.all(), self.flag.pk, act), "done")
        self.assertEqual(self.flags(), [NAME, f"{NAME}_written"])

    def test_the_block_commits_before_the_refusal_is_raised(self):
        committed = []

        def act(row):
            transaction.on_commit(lambda: committed.append(True))
            return row, OrderCancellationException("refused")

        with self.assertRaises(OrderCancellationException):
            act_under_row_lock(FeatureFlag.objects.all(), self.flag.pk, act)

        self.assertEqual(committed, [True])
