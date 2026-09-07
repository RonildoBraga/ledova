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


@patch.object(TransferService, "_schedule_confirmation_checks")
@patch("wallets.services.transfers.get_blockchain_client")
class TransferFeeAccountingTest(BroadcastTransferGuardTestCase):

    def setUp(self):
        super().setUp()
        self.native = native_asset_for_chain(self.wallet.chain)
        self.token = self.usdc()
        self.token_holding = Holding.objects.create(wallet=self.wallet, asset=self.token, quantity=Decimal("100"))
        self.native_holding = Holding.objects.create(wallet=self.wallet, asset=self.native, quantity=Decimal("5"))

    def quantities(self):
        self.token_holding.refresh_from_db()
        self.native_holding.refresh_from_db()
        return self.token_holding.quantity, self.native_holding.quantity

    def send_token(self, get_client, tx_hash, fee="0.002"):
        get_client.return_value.broadcast_transaction.return_value = tx_hash
        return self.broadcast(
            signed_transaction=sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, 1_500_000)),
            to_address=RECIPIENT,
            amount="1.5",
            token_contract=USDC_CONTRACT,
            transaction_fee=fee,
        )

    def test_the_gas_fee_leaves_the_native_holding_not_the_transferred_token(self, get_client, schedule):
        response = self.send_token(get_client, "0xerc20fee")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("4.998")))

    def test_a_native_send_takes_the_amount_and_the_fee_from_the_one_holding(self, get_client, schedule):
        get_client.return_value.broadcast_transaction.return_value = "0xnativefee"

        response = self.broadcast(
            signed_transaction=sign(to=RECIPIENT, value=25 * 10**16),
            to_address=RECIPIENT,
            amount="0.25",
            transaction_fee="0.002",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("4.748")))

    def test_a_failed_transfer_returns_the_fee_it_took_as_well_as_the_amount(self, get_client, schedule):
        self.send_token(get_client, "0xerc20failed")

        with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
            TransactionConfirmationService.fail_transaction("0xerc20failed", reason="reverted")

        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_a_failed_native_send_returns_both_from_the_one_holding(self, get_client, schedule):
        get_client.return_value.broadcast_transaction.return_value = "0xnativefailed"
        self.broadcast(
            signed_transaction=sign(to=RECIPIENT, value=25 * 10**16),
            to_address=RECIPIENT,
            amount="0.25",
            transaction_fee="0.002",
        )

        with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
            TransactionConfirmationService.fail_transaction("0xnativefailed", reason="reverted")

        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_confirmation_resyncs_the_native_holding_as_well_as_the_transferred_one(self, get_client, schedule):
        self.send_token(get_client, "0xerc20confirmed")

        with patch("wallets.services.transaction_confirmation.sync_holding") as sync:
            with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
                TransactionConfirmationService.confirm_transaction("0xerc20confirmed", block_number=1)

        synced = {call.args[1].symbol for call in sync.call_args_list}
        self.assertEqual(synced, {self.token.symbol, self.native.symbol})

    def test_a_native_confirmation_syncs_that_holding_once(self, get_client, schedule):
        get_client.return_value.broadcast_transaction.return_value = "0xnativeconfirmed"
        self.broadcast(
            signed_transaction=sign(to=RECIPIENT, value=25 * 10**16),
            to_address=RECIPIENT,
            amount="0.25",
            transaction_fee="0.002",
        )

        with patch("wallets.services.transaction_confirmation.sync_holding") as sync:
            with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
                TransactionConfirmationService.confirm_transaction("0xnativeconfirmed", block_number=1)

        self.assertEqual([call.args[1].symbol for call in sync.call_args_list], [self.native.symbol])

    def test_a_fee_larger_than_the_native_holding_floors_at_zero_rather_than_going_negative(self, get_client, schedule):
        self.send_token(get_client, "0xerc20bigfee", fee="500")

        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("0")))

    def test_the_row_still_records_the_declared_fee_as_an_estimate_only(self, get_client, schedule):
        self.send_token(get_client, "0xerc20estimate")

        tx = Transaction.objects.get(tx_hash="0xerc20estimate")
        self.assertEqual(tx.transaction_fee_estimated, Decimal("0.002"))
        self.assertIsNone(tx.transaction_fee)
        self.assertEqual(tx.asset.symbol, self.token.symbol)
