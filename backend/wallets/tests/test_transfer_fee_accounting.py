from decimal import Decimal
from unittest.mock import Mock, patch

from django.conf import settings
from web3 import Web3

from assets.services.identity import native_asset_for_chain
from wallets.models import Holding, Transaction
from wallets.services import transfers
from wallets.services.transaction_confirmation import TransactionConfirmationService
from wallets.tests.test_broadcast_transfer_guard import (
    RECIPIENT,
    USDC_CONTRACT,
    BroadcastTransferGuardTestCase,
    erc20_transfer_data,
    sign,
)


@patch.object(transfers, "_schedule_confirmation_checks")
@patch("wallets.services.submissions.get_blockchain_client")
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

    def record_acknowledgement(self, get_client, signed):
        self.tx_hash = Web3.keccak(hexstr=signed).to_0x_hex()
        get_client.return_value.assert_expected_chain = Mock(return_value=settings.BLOCKCHAIN_CHAIN_ID)
        get_client.return_value.get_transaction_receipt.return_value = None
        get_client.return_value.broadcast_transaction.return_value = self.tx_hash

    def send_token(self, get_client, fee="0.002", declared_fee=None):
        signed = sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, 1_500_000), gas=int(Decimal(fee) * 10**9))
        self.record_acknowledgement(get_client, signed)
        return self.broadcast(
            signed_transaction=signed,
            to_address=RECIPIENT,
            amount="1.5",
            token_contract=USDC_CONTRACT,
            transaction_fee=fee if declared_fee is None else declared_fee,
        )

    def send_native(self, get_client):
        signed = sign(to=RECIPIENT, value=25 * 10**16, gas=2_000_000)
        self.record_acknowledgement(get_client, signed)
        return self.broadcast(signed_transaction=signed, to_address=RECIPIENT, amount="0.25", transaction_fee="0.002")

    def test_the_gas_fee_leaves_the_native_holding_not_the_transferred_token(self, get_client, schedule):
        response = self.send_token(get_client)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("4.998")))

    def test_a_native_send_takes_the_amount_and_the_fee_from_the_one_holding(self, get_client, schedule):
        response = self.send_native(get_client)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("4.748")))

    def test_a_failed_transfer_returns_the_fee_it_took_as_well_as_the_amount(self, get_client, schedule):
        self.send_token(get_client)

        with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
            TransactionConfirmationService.fail_transaction(self.tx_hash, reason="reverted", wallet=self.wallet)

        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_a_failed_native_send_returns_both_from_the_one_holding(self, get_client, schedule):
        self.send_native(get_client)

        with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
            TransactionConfirmationService.fail_transaction(self.tx_hash, reason="reverted", wallet=self.wallet)

        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_confirmation_resyncs_the_native_holding_as_well_as_the_transferred_one(self, get_client, schedule):
        self.send_token(get_client)

        with patch("wallets.services.transaction_confirmation.sync_holding") as sync:
            with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
                TransactionConfirmationService.confirm_transaction(self.tx_hash, block_number=1, wallet=self.wallet)

        synced = {call.args[1].symbol for call in sync.call_args_list}
        self.assertEqual(synced, {self.token.symbol, self.native.symbol})

    def test_a_native_confirmation_syncs_that_holding_once(self, get_client, schedule):
        self.send_native(get_client)

        with patch("wallets.services.transaction_confirmation.sync_holding") as sync:
            with patch.object(TransactionConfirmationService, "_notify_wallet_users"):
                TransactionConfirmationService.confirm_transaction(self.tx_hash, block_number=1, wallet=self.wallet)

        self.assertEqual([call.args[1].symbol for call in sync.call_args_list], [self.native.symbol])

    def test_a_fee_larger_than_the_native_holding_floors_at_zero_rather_than_going_negative(self, get_client, schedule):
        self.send_token(get_client, fee="500")

        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("0")))

    def test_the_row_records_the_signed_fee_cap_and_ignores_a_false_declared_estimate(self, get_client, schedule):
        self.send_token(get_client, declared_fee="0")

        tx = Transaction.objects.get(tx_hash=self.tx_hash)
        self.assertEqual(tx.transaction_fee_estimated, Decimal("0.002"))
        self.assertIsNone(tx.transaction_fee)
        self.assertEqual(tx.asset.symbol, self.token.symbol)
