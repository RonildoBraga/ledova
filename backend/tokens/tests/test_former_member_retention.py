from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from tokens.models import FormerHolder, ShareIssuance
from tokens.models.choices import IDENTITY_STAMPED, IssuanceStatus
from tokens.services.former_holders import (
    cessations_in,
    fold_former_holders,
    purge_former_holders,
)
from tokens.tests.test_the_fold_that_writes_former_members import (
    ALICE,
    BOB,
    ZERO,
    FoldTestFixtures,
    transfer,
)
from whitelist.models import HolderType
from whitelist.services.identity import HolderIdentity


class FormerMemberRetentionTest(FoldTestFixtures, TestCase):
    def test_a_full_history_refold_cannot_resurrect_a_record_the_retention_sweep_removed(self):
        entries = [transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)]
        self.a_fold(entries)
        future = timezone.now() + timedelta(days=2558)
        self.assertEqual(purge_former_holders(now=future), 1)
        with patch("tokens.services.former_holders.timezone.now", return_value=future):
            result = self.a_fold(entries)
        self.assertEqual(result["written"], 0)
        self.assertFalse(FormerHolder.objects.filter(token=self.token).exists())

    def test_a_refold_does_not_look_up_or_overwrite_already_recorded_identity(self):
        first = HolderIdentity(HolderType.MEMBER.value, "Original holder", "Original address", "Active")
        with patch("tokens.services.former_holders.identities_for", return_value={ALICE.lower(): first}):
            self.a_fold([transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)])
        with patch("tokens.services.former_holders.identities_for", return_value={}) as identities:
            self.a_fold([transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)])
        identities.assert_called_once_with([])
        row = FormerHolder.objects.get(token=self.token)
        self.assertEqual((row.name, row.residential_address), ("Original holder", "Original address"))

    def test_retention_is_rechecked_after_a_slow_provider_read_crosses_the_cutoff(self):
        started = timezone.now()
        now = [started]
        entries = [transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)]
        reader = self.reader(entries)

        def late_date(block):
            now[0] = started + timedelta(days=1)
            return started.date() - timedelta(days=2557)

        reader.block_date.side_effect = late_date
        with patch("tokens.services.former_holders.timezone.now", side_effect=lambda: now[0]):
            result = fold_former_holders(self.token, reader=reader)
        self.assertEqual(result["written"], 0)
        self.assertFalse(FormerHolder.objects.filter(token=self.token).exists())

    def test_an_allotment_stamp_survives_the_loss_of_the_live_profile(self):
        ShareIssuance.objects.create(
            token=self.token,
            recipient_address=ALICE,
            recipient_name="Holder at allotment",
            recipient_residential_address="Recorded address",
            identity_stamped_at=timezone.now() - timedelta(days=300),
            status=IssuanceStatus.COMPLETED,
            amount="100",
        )
        with patch("tokens.services.former_holders.identities_for", return_value={}):
            self.a_fold([transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)])
        row = FormerHolder.objects.get(token=self.token)
        self.assertEqual(row.name, "Holder at allotment")
        self.assertEqual(row.residential_address, "Recorded address")
        self.assertEqual(row.identity_source, IDENTITY_STAMPED)

    def test_an_unreadable_later_block_leaves_no_partial_records_or_freshness_claim(self):
        reader = self.reader(
            [
                transfer(ZERO, ALICE, 100, 10),
                transfer(ALICE, BOB, 100, 20),
                transfer(BOB, ZERO, 100, 30),
            ]
        )
        reader.block_date.side_effect = [timezone.now().date(), RuntimeError("Synthetic unavailable block")]
        with self.assertRaises(RuntimeError):
            fold_former_holders(self.token, reader=reader)
        self.assertFalse(FormerHolder.objects.filter(token=self.token).exists())
        self.token.refresh_from_db()
        self.assertIsNone(self.token.former_holders_folded_at)
        self.assertIsNone(self.token.former_holders_block)

    def test_a_worker_that_read_an_older_head_cannot_move_the_freshness_marker_backwards(self):
        entries = [transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)]
        self.a_fold(entries)
        self.token.refresh_from_db()
        stamp = self.token.former_holders_folded_at
        reader = self.reader(entries)
        reader.finalized_block.return_value = 50
        result = fold_former_holders(self.token, reader=reader)
        self.token.refresh_from_db()
        self.assertEqual(result["block"], 99)
        self.assertEqual(self.token.former_holders_block, 99)
        self.assertEqual(self.token.former_holders_folded_at, stamp)

    def test_partial_history_is_refused_without_claiming_the_register_is_current(self):
        reader = self.reader([transfer(ALICE, BOB, 100, 20)])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            fold_former_holders(self.token, reader=reader)
        self.token.refresh_from_db()
        self.assertIsNone(self.token.former_holders_folded_at)
        self.assertFalse(FormerHolder.objects.filter(token=self.token).exists())

    def test_address_casing_does_not_split_one_holders_balance(self):
        entries = [transfer(ZERO, ALICE.lower(), 100, 10), transfer(ALICE, BOB, 100, 20)]
        self.assertEqual(cessations_in(entries), [{"address": ALICE, "block_number": 20, "shares": 100}])

    def test_a_self_transfer_does_not_create_a_former_member(self):
        self.assertEqual(cessations_in([transfer(ZERO, ALICE, 100, 10), transfer(ALICE, ALICE, 100, 20)]), [])

    @skipUnless(connection.vendor == "postgresql", "Exact large NUMERIC storage requires PostgreSQL")
    def test_a_large_chain_quantity_is_retained_exactly(self):
        shares = 10**30 + 1
        self.a_fold([transfer(ZERO, ALICE, shares, 10), transfer(ALICE, BOB, shares, 20)])
        row = FormerHolder.objects.get(token=self.token)
        self.assertEqual(row.shares_at_cessation, shares)

    def test_repeated_provider_events_are_refused(self):
        event = transfer(ZERO, ALICE, 100, 10)
        with self.assertRaisesRegex(ValueError, "repeats"):
            cessations_in([event, event])

    @override_settings(FORMER_MEMBER_RETENTION_DAYS=1)
    def test_a_shortened_retention_setting_cannot_delete_or_rebuild_the_register(self):
        with self.assertRaises(ImproperlyConfigured):
            purge_former_holders()
        with self.assertRaises(ImproperlyConfigured):
            fold_former_holders(self.token, reader=self.reader([]))
