from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from shared.tests.tenants import make_tenant
from tokens.exceptions import InvalidTokenStateException, IssuanceRefusedException
from tokens.models import CapitalIncreaseRequest, RequestStatus, ShareToken
from tokens.services import ShareTokenService
from tokens.services.capital_increase import submit_capital_increase

RECEIPT = {"status": 1, "blockNumber": 9, "blockHash": bytes.fromhex("ab" * 32), "gasUsed": 21000}


class SupersededCapitalIncreaseTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("superseded")
        self.token = self.tenant.deployed_token
        self.request = self.tenant.capital_increase
        self.request.status = RequestStatus.FAILED
        self.request.review_notes = "The reviewer approved the original board resolution."
        self.request.save(update_fields=["status", "review_notes", "updated_at"])
        self.record = BlockchainTransaction.objects.create(
            tx_type=TransactionType.OTHER,
            status=TransactionStatus.SUBMITTED,
            tx_hash="0x" + "11" * 32,
            function_name="setAuthorizedShares",
            related_model=CapitalIncreaseRequest._meta.label,
            related_uuid=self.request.uuid,
        )
        self.service = ShareTokenService.__new__(ShareTokenService)
        self.service.chain_client = Mock()
        self.service.chain_client.get_transaction_receipt.return_value = RECEIPT
        self.service.share_supply = Mock(return_value=(1000, 0))
        self.service.increase_authorized_shares = Mock()

    def raise_cap(self, current, recorded=True):
        ShareToken.objects.filter(pk=self.token.pk).update(total_supply=str(current))
        if not recorded:
            return None
        return CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=current - 1000,
            new_authorized_total=current,
            purpose="Later increase",
            board_resolution_reference="LATER-BOARD",
            status=RequestStatus.EXECUTED,
            executed_at=timezone.now(),
        )

    def assert_superseded(self, current, later):
        notes = self.request.review_notes
        with self.assertRaises(IssuanceRefusedException) as refusal:
            self.service.execute_request(self.request)

        reason = str(refusal.exception.detail)
        self.assertIn(str(self.request.new_authorized_total), reason)
        self.assertIn(str(current), reason)
        self.assertIn("Submit a new capital-increase request", reason)
        if later:
            self.assertIn(str(later.uuid), reason)
        else:
            self.assertIn("No completed request identifies the current cap", reason)
        self.request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((self.request.status, self.token.total_supply), ("superseded", str(current)))
        self.assertEqual(self.request.rejection_reason, reason)
        self.assertEqual(self.request.review_notes, notes)
        self.assertIsNone(self.request.executed_at)
        self.assertFalse(self.request.can_be_executed or self.request.can_be_approved or self.request.can_be_edited)
        self.service.chain_client.get_transaction_receipt.assert_not_called()
        self.service.chain_client.send_transaction.assert_not_called()
        self.service.share_supply.assert_not_called()
        self.service.increase_authorized_shares.assert_not_called()

    def test_a_resumed_request_below_a_later_cap_is_permanently_refused(self):
        later = self.raise_cap(1500)

        self.assert_superseded(1500, later)

        with self.assertRaises(InvalidTokenStateException):
            self.service.execute_request(self.request)
        replacement = CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=100,
            new_authorized_total=1600,
            purpose="New request after supersession",
            board_resolution_reference="NEW-BOARD",
        )
        submit_capital_increase(replacement, self.tenant.user)
        self.assertEqual(replacement.status, RequestStatus.SUBMITTED)

    def test_a_request_equal_to_the_current_cap_is_also_superseded(self):
        later = self.raise_cap(1100)

        self.assert_superseded(1100, later)

    def test_an_unattributed_cap_does_not_invent_an_overtaking_request(self):
        self.raise_cap(1500, recorded=False)

        self.assert_superseded(1500, None)

    def test_an_approved_request_without_a_transaction_is_refused_before_sending(self):
        self.record.delete()
        self.request.status = RequestStatus.APPROVED
        self.request.save(update_fields=["status", "updated_at"])
        later = self.raise_cap(1500)

        self.assert_superseded(1500, later)

    def test_the_sweep_retires_an_overtaken_executing_request_before_reading_the_chain(self):
        self.request.status = RequestStatus.EXECUTING
        self.request.save(update_fields=["status", "updated_at"])
        later = self.raise_cap(1500)

        self.assertEqual(self.service.resolve_executing_capital_increase(self.request), "superseded")

        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "superseded")
        self.assertIn(str(later.uuid), self.request.rejection_reason)
        self.service.chain_client.get_transaction_receipt.assert_not_called()

    def test_the_sweep_rechecks_the_cap_after_reading_a_receipt(self):
        self.request.status = RequestStatus.EXECUTING
        self.request.save(update_fields=["status", "updated_at"])

        def receipt_after_the_cap_changed(tx_hash):
            self.raise_cap(1500)
            return RECEIPT

        self.service.chain_client.get_transaction_receipt.side_effect = receipt_after_the_cap_changed

        self.assertEqual(self.service.resolve_executing_capital_increase(self.request), "superseded")

        self.request.refresh_from_db()
        self.token.refresh_from_db()
        self.record.refresh_from_db()
        self.assertEqual((self.request.status, self.token.total_supply), ("superseded", "1500"))
        self.assertEqual(self.record.status, TransactionStatus.CONFIRMED)

    def test_a_late_revert_does_not_make_a_terminal_request_retryable_again(self):
        self.request.status = RequestStatus.EXECUTING
        self.request.save(update_fields=["status", "updated_at"])

        def receipt_after_supersession(tx_hash):
            CapitalIncreaseRequest.objects.filter(pk=self.request.pk).update(
                status="superseded", rejection_reason="A newer cap already replaced this request."
            )
            return {**RECEIPT, "status": 0}

        self.service.chain_client.get_transaction_receipt.side_effect = receipt_after_supersession

        self.assertIsNone(self.service.resolve_executing_capital_increase(self.request))

        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "superseded")
        self.assertFalse(self.request.can_be_executed)
