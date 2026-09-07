from decimal import Decimal
from unittest.mock import patch

from assets.services.identity import native_asset_for_chain
from wallets.models import Holding, Transaction
from wallets.services.transaction_confirmation import TransactionConfirmationService
from wallets.services.transfers import TransferService
from wallets.tests.test_broadcast_transfer_guard import (
    RECIPIENT,
    USDC_CONTRACT,
    BroadcastTransferGuardTestCase,
    erc20_transfer_data,
    sign,
)

FEE = "0.002"


@patch.object(TransferService, "_schedule_confirmation_checks")
@patch("wallets.services.transfers.get_blockchain_client")
class ReversingOnlyWhatWasDeductedTest(BroadcastTransferGuardTestCase):

    def setUp(self):
        super().setUp()
        self.native = native_asset_for_chain(self.wallet.chain)
        self.token = self.usdc()

    def hold(self, asset, quantity):
        return Holding.objects.create(wallet=self.wallet, asset=asset, quantity=Decimal(quantity))

    def quantity(self, asset):
        holding = Holding.objects.filter(wallet=self.wallet, asset=asset).first()
        return None if holding is None else holding.quantity

    def send_token(self, get_client, tx_hash, amount="1.5", raw=1_500_000, fee=FEE):
        get_client.return_value.broadcast_transaction.return_value = tx_hash
        return self.broadcast(
            signed_transaction=sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, raw)),
            to_address=RECIPIENT,
            amount=amount,
            token_contract=USDC_CONTRACT,
            transaction_fee=fee,
        )

    def send_native(self, get_client, tx_hash, amount="0.25", value=25 * 10**16, fee=FEE):
        get_client.return_value.broadcast_transaction.return_value = tx_hash
        return self.broadcast(
            signed_transaction=sign(to=RECIPIENT, value=value),
            to_address=RECIPIENT,
            amount=amount,
            transaction_fee=fee,
        )

    def fail_transfer(self, tx_hash):
        with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
            return TransactionConfirmationService.fail_transaction(tx_hash, reason="reverted")

    def test_a_wallet_with_no_native_holding_is_not_given_one_by_a_failed_transfer(self, get_client, schedule):
        self.hold(self.token, "100")

        self.assertEqual(self.send_token(get_client, "0xnonative").status_code, 200)
        self.assertEqual(self.quantity(self.native), Decimal("0"))
        self.fail_transfer("0xnonative")

        self.assertEqual(self.quantity(self.native), Decimal("0"))
        self.assertEqual(self.quantity(self.token), Decimal("100"))

    def test_a_transfer_larger_than_the_holding_comes_back_to_where_it_started(self, get_client, schedule):
        self.hold(self.token, "1")
        self.hold(self.native, "5")

        self.assertEqual(self.send_token(get_client, "0xshorttoken").status_code, 200)
        self.assertEqual(self.quantity(self.token), Decimal("0"))
        self.fail_transfer("0xshorttoken")

        self.assertEqual(self.quantity(self.token), Decimal("1"))
        self.assertEqual(self.quantity(self.native), Decimal("5"))

    def test_a_fee_larger_than_the_native_holding_comes_back_to_where_it_started(self, get_client, schedule):
        self.hold(self.token, "100")
        self.hold(self.native, "5")

        self.assertEqual(self.send_token(get_client, "0xbigfee", fee="500").status_code, 200)
        self.assertEqual(self.quantity(self.native), Decimal("0"))
        self.fail_transfer("0xbigfee")

        self.assertEqual(self.quantity(self.native), Decimal("5"))
        self.assertEqual(self.quantity(self.token), Decimal("100"))

    def test_a_native_send_larger_than_the_one_holding_comes_back_to_where_it_started(self, get_client, schedule):
        self.hold(self.native, "0.1")

        self.assertEqual(self.send_native(get_client, "0xshortnative").status_code, 200)
        self.assertEqual(self.quantity(self.native), Decimal("0"))
        self.fail_transfer("0xshortnative")

        self.assertEqual(self.quantity(self.native), Decimal("0.1"))

    def test_an_unclamped_transfer_still_comes_back_in_full(self, get_client, schedule):
        self.hold(self.token, "100")
        self.hold(self.native, "5")

        self.assertEqual(self.send_token(get_client, "0xordinary").status_code, 200)
        self.assertEqual((self.quantity(self.token), self.quantity(self.native)), (Decimal("98.5"), Decimal("4.998")))
        self.fail_transfer("0xordinary")

        self.assertEqual((self.quantity(self.token), self.quantity(self.native)), (Decimal("100"), Decimal("5")))

    def test_the_row_records_what_each_holding_actually_gave_up(self, get_client, schedule):
        self.hold(self.token, "100")
        self.hold(self.native, "5")
        self.send_token(get_client, "0xrecorded", fee="500")

        tx = Transaction.objects.get(tx_hash="0xrecorded")

        self.assertEqual(tx.deducted_amount, Decimal("1.5"))
        self.assertEqual(tx.deducted_fee, Decimal("5"))
        self.assertEqual(tx.transaction_fee_estimated, Decimal("500"))

    def test_a_native_send_records_one_deduction_and_no_separate_fee(self, get_client, schedule):
        self.hold(self.native, "5")
        self.send_native(get_client, "0xnativerecorded")

        tx = Transaction.objects.get(tx_hash="0xnativerecorded")

        self.assertEqual(tx.deducted_amount, Decimal("0.252"))
        self.assertIsNone(tx.deducted_fee)

    def test_a_row_that_predates_the_record_reverses_the_way_it_always_did(self, get_client, schedule):
        self.hold(self.token, "100")
        self.hold(self.native, "5")
        self.send_token(get_client, "0xlegacy")
        Transaction.objects.filter(tx_hash="0xlegacy").update(deducted_amount=None, deducted_fee=None)

        self.fail_transfer("0xlegacy")

        self.assertEqual((self.quantity(self.token), self.quantity(self.native)), (Decimal("100"), Decimal("5")))
