from datetime import date, timedelta
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from shared.tests.tenants import make_tenant
from tokens.models import FormerHolder, ShareToken
from tokens.models.choices import IDENTITY_UNKNOWN
from tokens.services.former_holders import (
    STALE_AFTER,
    cessations_in,
    fold_former_holders,
    fold_is_stale,
    purge_former_holders,
)
from tokens.services.register import (
    AS_AT_ROW,
    FORMER_MEMBERS_HEADING,
    NEVER_FOLDED,
    STALE,
    export_rows,
)

ALICE = "0x" + "a1" * 20
BOB = "0x" + "b2" * 20
ZERO = "0x" + "00" * 20


def transfer(sender, recipient, value, block, index=0):
    return {"from": sender, "to": recipient, "value": value, "block_number": block, "log_index": index}


class WhatTheLogSaysAboutCeasingTest(TestCase):

    def test_a_balance_reaching_zero_is_a_cessation_carrying_what_was_held(self):
        entries = [transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)]

        self.assertEqual(cessations_in(entries), [{"address": ALICE, "block_number": 20, "shares": 100}])

    def test_a_mint_is_not_a_cessation_for_the_zero_address(self):
        entries = [transfer(ZERO, ALICE, 100, 10)]

        self.assertEqual(cessations_in(entries), [])

    def test_a_burn_ends_the_holder_that_burned(self):
        entries = [transfer(ZERO, ALICE, 100, 10), transfer(ALICE, ZERO, 100, 30)]

        self.assertEqual(cessations_in(entries), [{"address": ALICE, "block_number": 30, "shares": 100}])

    def test_a_partial_transfer_out_is_not_a_cessation(self):
        entries = [transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 40, 20)]

        self.assertEqual(cessations_in(entries), [])

    def test_a_holder_that_ceased_and_rejoined_and_ceased_again_is_two_cessations(self):
        entries = [
            transfer(ZERO, ALICE, 100, 10),
            transfer(ALICE, BOB, 100, 20),
            transfer(BOB, ALICE, 60, 30),
            transfer(ALICE, BOB, 60, 40),
        ]

        self.assertEqual(
            [
                (row["address"], row["block_number"], row["shares"])
                for row in cessations_in(entries)
                if row["address"] == ALICE
            ],
            [(ALICE, 20, 100), (ALICE, 40, 60)],
        )

    def test_two_transfers_in_one_block_are_read_in_log_index_order(self):
        entries = [
            transfer(ZERO, ALICE, 100, 10),
            transfer(ALICE, BOB, 100, 20, index=0),
            transfer(BOB, ALICE, 100, 20, index=1),
        ]

        cessations = cessations_in(entries)

        self.assertEqual([(row["address"], row["shares"]) for row in cessations], [(ALICE, 100), (BOB, 100)])

    def test_the_same_block_read_the_other_way_round_says_something_different(self):
        entries = [
            transfer(ZERO, ALICE, 100, 10),
            transfer(BOB, ALICE, 100, 20, index=1),
            transfer(ALICE, BOB, 100, 20, index=0),
        ]

        self.assertNotEqual(cessations_in(entries), cessations_in(sorted(entries, key=lambda e: e["log_index"])))


class TheReaderReturnsTheLogInTheOrderItHappenedTest(TestCase):

    @staticmethod
    def a_service(logs):
        from tokens.services.share_token_service import ShareTokenService

        service = ShareTokenService.__new__(ShareTokenService)
        contract = Mock()
        contract.events.Transfer.return_value.get_logs.return_value = logs
        service.load_share_token = Mock(return_value=contract)
        return service

    @staticmethod
    def a_log(sender, recipient, value, block, index):
        return {
            "args": {"from": sender, "to": recipient, "value": value},
            "blockNumber": block,
            "logIndex": index,
        }

    def test_entries_come_back_ordered_by_block_then_log_index(self):
        service = self.a_service(
            [
                self.a_log(ALICE, BOB, 5, 20, 3),
                self.a_log(BOB, ALICE, 5, 20, 1),
                self.a_log(ZERO, ALICE, 5, 10, 9),
            ]
        )

        entries = service.transfer_entries("0xcontract", 1, 30)

        self.assertEqual([(row["block_number"], row["log_index"]) for row in entries], [(10, 9), (20, 1), (20, 3)])

    def test_a_provider_that_answers_out_of_order_does_not_change_the_answer(self):
        forwards = self.a_service([self.a_log(ZERO, ALICE, 5, 10, 0), self.a_log(ALICE, BOB, 5, 20, 0)])
        backwards = self.a_service([self.a_log(ALICE, BOB, 5, 20, 0), self.a_log(ZERO, ALICE, 5, 10, 0)])

        self.assertEqual(
            cessations_in(forwards.transfer_entries("0xc", 1, 30)),
            cessations_in(backwards.transfer_entries("0xc", 1, 30)),
        )


class TheFoldWritesEachCessationOnceTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("fold")
        self.token = self.tenant.deployed_token

    def reader(self, entries):
        reader = Mock()
        reader.head_block.return_value = 99
        reader.transfer_entries.return_value = entries
        reader.block_date.side_effect = lambda block: date(2026, 3, 1) + timedelta(days=block)
        reader.deployment_block.return_value = 1
        return reader

    def a_fold(self, entries):
        reader = self.reader(entries)
        self.token.deployment_transaction = None
        ShareToken.objects.filter(pk=self.token.pk).update(deployment_tx_hash="0x" + "de" * 32)
        self.token.refresh_from_db()
        return fold_former_holders(self.token, reader=reader)

    def test_a_cessation_becomes_a_row_the_register_can_show(self):
        self.a_fold([transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)])

        row = FormerHolder.objects.get(token=self.token)
        self.assertEqual((row.wallet_address, row.ceased_at_block, row.shares_at_cessation), (ALICE, 20, 100))
        self.assertEqual(row.ceased_on, date(2026, 3, 1) + timedelta(days=20))
        self.assertEqual(row.identity_source, IDENTITY_UNKNOWN)
        self.assertEqual(row.owner_id, self.tenant.company.owner_id)

    def test_folding_the_same_range_again_writes_nothing_new(self):
        entries = [transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)]

        first = self.a_fold(entries)
        second = self.a_fold(entries)

        self.assertEqual((first["written"], second["written"]), (1, 0))
        self.assertEqual(FormerHolder.objects.filter(token=self.token).count(), 1)

    def test_the_fold_records_where_it_reached(self):
        self.a_fold([transfer(ZERO, ALICE, 100, 10), transfer(ALICE, BOB, 100, 20)])

        self.token.refresh_from_db()
        self.assertEqual(self.token.former_holders_block, 99)
        self.assertIsNotNone(self.token.former_holders_folded_at)


class WhetherTheRegisterAdmitsItIsStaleTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("stale")
        self.token = self.tenant.deployed_token

    def folded(self, ago):
        ShareToken.objects.filter(pk=self.token.pk).update(
            former_holders_folded_at=timezone.now() - ago, former_holders_block=500
        )
        self.token.refresh_from_db()

    def test_a_share_class_never_folded_is_stale(self):
        self.assertTrue(fold_is_stale(self.token))

    def test_a_fold_inside_the_window_is_not_stale(self):
        self.folded(STALE_AFTER - timedelta(minutes=1))

        self.assertFalse(fold_is_stale(self.token))

    def test_a_fold_older_than_the_window_is_stale(self):
        self.folded(STALE_AFTER + timedelta(minutes=1))

        self.assertTrue(fold_is_stale(self.token))


class WhatTheExportSaysAboutFormerMembersTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("export")
        self.token = self.tenant.deployed_token

    def rows(self):
        from unittest.mock import patch

        with patch("tokens.services.register.token_register", return_value=([], 0)):
            return export_rows(self.token, self.tenant.user)

    def a_former_member(self):
        return FormerHolder.objects.create(
            token=self.token,
            wallet_address=ALICE,
            ceased_on=date(2026, 3, 14),
            ceased_at_block=42,
            shares_at_cessation=1000,
            name="Bob Byer",
        )

    def test_the_section_has_its_own_heading_and_the_row(self):
        self.a_former_member()

        rows = self.rows()

        self.assertIn([FORMER_MEMBERS_HEADING], rows)
        self.assertIn(["Bob Byer", "", ALICE, "1000", "2026-03-14", "Never identified while it held shares"], rows)

    def test_a_register_never_folded_says_so_and_says_stale(self):
        as_at = [row for row in self.rows() if row and row[0] == AS_AT_ROW][0]

        self.assertEqual(as_at, [AS_AT_ROW, NEVER_FOLDED, STALE])

    def test_a_fresh_fold_reports_its_block_and_does_not_say_stale(self):
        ShareToken.objects.filter(pk=self.token.pk).update(
            former_holders_folded_at=timezone.now(), former_holders_block=777
        )
        self.token.refresh_from_db()

        as_at = [row for row in self.rows() if row and row[0] == AS_AT_ROW][0]

        self.assertIn("block 777", as_at)
        self.assertNotIn(STALE, as_at)


class TheRetentionClockIsTheOnlyDeletionTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("retention")
        self.token = self.tenant.deployed_token

    def a_cessation(self, ceased_on, block):
        return FormerHolder.objects.create(
            token=self.token,
            wallet_address=ALICE,
            ceased_on=ceased_on,
            ceased_at_block=block,
            shares_at_cessation=10,
        )

    def test_a_record_past_seven_years_from_when_they_ceased_is_removed(self):
        self.a_cessation(timezone.now().date() - timedelta(days=2558), 1)

        self.assertEqual(purge_former_holders(), 1)
        self.assertEqual(FormerHolder.objects.count(), 0)

    def test_a_record_inside_the_seven_years_is_kept(self):
        self.a_cessation(timezone.now().date() - timedelta(days=2556), 2)

        self.assertEqual(purge_former_holders(), 0)
        self.assertEqual(FormerHolder.objects.count(), 1)
