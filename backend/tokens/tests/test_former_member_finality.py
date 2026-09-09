from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from shared.tests.tenants import make_tenant
from tokens.models import FormerHolder
from tokens.services.former_holders import fold_former_holders
from tokens.services.share_token_service import ShareTokenService
from tokens.tasks.former_holders import fold_every_share_class
from tokens.tests.test_the_fold_that_writes_former_members import (
    ALICE,
    BOB,
    ZERO,
    FoldTestFixtures,
    transfer,
)


class FormerMemberFinalityTest(FoldTestFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.service = ShareTokenService.__new__(ShareTokenService)
        self.service.chain_client = Mock()
        self.provider = self.service.chain_client.w3.eth
        self.provider.block_number = 22
        self.finalized = 19
        self.entries = [transfer(ZERO, ALICE, 10, 10), transfer(ALICE, BOB, 10, 20)]
        self.service.deployment_block = Mock(return_value=1)
        self.service.load_share_token = Mock()
        self.contract = self.service.load_share_token.return_value
        self.contract.events.Transfer.return_value.get_logs.side_effect = self.logs
        self.provider.get_block.side_effect = self.block

    def block(self, number):
        if number == "finalized":
            return {"number": self.finalized}
        return {"number": number, "timestamp": int(timezone.now().timestamp())}

    def logs(self, from_block, to_block):
        return [
            {
                "blockNumber": entry["block_number"],
                "logIndex": entry["log_index"],
                "args": {key: entry[key] for key in ("from", "to", "value")},
            }
            for entry in self.entries
            if from_block <= entry["block_number"] <= to_block
        ]

    def test_a_head_cessation_that_is_reorganized_never_enters_the_register(self):
        first = fold_former_holders(self.token, reader=self.service)
        self.assertEqual((first["written"], first["block"]), (0, 19))
        self.assertFalse(FormerHolder.objects.filter(token=self.token).exists())
        self.entries.pop()
        self.finalized = 22
        self.assertEqual(fold_former_holders(self.token, reader=self.service)["written"], 0)
        self.assertFalse(FormerHolder.objects.filter(token=self.token).exists())

    def test_a_cessation_is_recorded_once_when_its_block_becomes_finalized(self):
        self.assertEqual(fold_former_holders(self.token, reader=self.service)["written"], 0)
        self.finalized = 20
        self.assertEqual(fold_former_holders(self.token, reader=self.service)["written"], 1)
        row = FormerHolder.objects.get(token=self.token)
        self.assertEqual((row.wallet_address, row.ceased_at_block, row.shares_at_cessation), (ALICE, 20, 10))
        self.assertEqual(fold_former_holders(self.token, reader=self.service)["written"], 0)

    def test_an_unavailable_finalized_block_does_not_fall_back_to_the_chain_head(self):
        self.finalized = 20
        fold_former_holders(self.token, reader=self.service)
        self.token.refresh_from_db()
        recorded_at = self.token.former_holders_folded_at

        def without_finality(number):
            if number == "finalized":
                raise RuntimeError("Synthetic unsupported finality")
            return self.block(number)

        self.provider.get_block.side_effect = without_finality
        with self.assertRaisesRegex(RuntimeError, "unsupported finality"):
            fold_former_holders(self.token, reader=self.service)
        self.token.refresh_from_db()
        self.assertEqual(self.token.former_holders_folded_at, recorded_at)
        self.assertEqual(FormerHolder.objects.filter(token=self.token).count(), 1)


class FormerMemberBatchRetryTest(FoldTestFixtures, TestCase):
    def test_one_unreadable_class_does_not_stop_the_rest_but_makes_the_batch_retryable(self):
        other = make_tenant("readable-class").deployed_token
        attempted = []

        def fold(token):
            attempted.append(token.pk)
            if token.pk == self.token.pk:
                raise RuntimeError("Synthetic transient provider outage")

        with patch("tokens.tasks.former_holders.fold_former_holders", side_effect=fold):
            with self.assertRaisesRegex(RuntimeError, "could not read 1 share classes"):
                fold_every_share_class()
        self.assertCountEqual(attempted, [self.token.pk, other.pk])

        with patch("tokens.tasks.former_holders.fold_former_holders") as retry:
            self.assertEqual(fold_every_share_class(), {"folded": 2})
        self.assertEqual(retry.call_count, 2)
