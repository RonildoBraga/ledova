from decimal import Decimal
from unittest.mock import patch

from web3 import Web3

from assets.services.identity import native_asset_for_chain
from wallets.models import Holding, Transaction
from wallets.services import transaction_confirmation
from wallets.tests.test_broadcast_transfer_guard import (
    RECIPIENT,
    USDC_CONTRACT,
    BroadcastTransferGuardTestCase,
    erc20_transfer_data,
    sign,
)


class LegacyTransferFeeAccountingTest(BroadcastTransferGuardTestCase):

    def setUp(self):
        super().setUp()
        self.native = native_asset_for_chain(self.wallet.chain)
        self.token = self.usdc()
        boundary = patch("wallets.services.transaction_confirmation.sync_holding", return_value=None)
        boundary.start()
        self.addCleanup(boundary.stop)
        self.token_holding = Holding.objects.create(wallet=self.wallet, asset=self.token, quantity=Decimal("100"))
        self.native_holding = Holding.objects.create(wallet=self.wallet, asset=self.native, quantity=Decimal("5"))

    def quantities(self):
        self.token_holding.refresh_from_db()
        self.native_holding.refresh_from_db()
        return self.token_holding.quantity, self.native_holding.quantity

    def send_token(self, fee="0.002"):
        signed = sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, 1_500_000), gas=int(Decimal(fee) * 10**9))
        self.tx_hash = Web3.keccak(hexstr=signed).to_0x_hex()
        return transaction_confirmation.create_pending_transaction(
            self.wallet,
            self.tx_hash,
            RECIPIENT,
            Decimal("1.5"),
            transaction_fee=Decimal(fee),
            token_contract=USDC_CONTRACT,
        )

    def send_native(self):
        signed = sign(to=RECIPIENT, value=25 * 10**16, gas=2_000_000)
        self.tx_hash = Web3.keccak(hexstr=signed).to_0x_hex()
        return transaction_confirmation.create_pending_transaction(
            self.wallet, self.tx_hash, RECIPIENT, Decimal("0.25"), transaction_fee=Decimal("0.002")
        )

    def test_the_gas_fee_leaves_the_native_holding_not_the_transferred_token(self):
        response = self.send_token()

        self.assertEqual(response["status"], "pending")
        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("4.998")))

    def test_a_native_send_takes_the_amount_and_the_fee_from_the_one_holding(self):
        response = self.send_native()

        self.assertEqual(response["status"], "pending")
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("4.748")))

    def test_a_failed_transfer_returns_the_fee_it_took_as_well_as_the_amount(self):
        self.send_token()

        with patch.object(transaction_confirmation, "_notify_wallet_users"):
            transaction_confirmation.fail_transaction(self.tx_hash, reason="reverted", wallet=self.wallet)

        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_a_failed_native_send_returns_both_from_the_one_holding(self):
        self.send_native()

        with patch.object(transaction_confirmation, "_notify_wallet_users"):
            transaction_confirmation.fail_transaction(self.tx_hash, reason="reverted", wallet=self.wallet)

        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_confirmation_resyncs_the_native_holding_as_well_as_the_transferred_one(self):
        self.send_token()

        with patch("wallets.services.transaction_confirmation.sync_holding") as sync:
            with patch.object(transaction_confirmation, "_notify_wallet_users"):
                transaction_confirmation.confirm_transaction(self.tx_hash, block_number=1, wallet=self.wallet)

        synced = {call.args[1].symbol for call in sync.call_args_list}
        self.assertEqual(synced, {self.token.symbol, self.native.symbol})

    def test_a_native_confirmation_syncs_that_holding_once(self):
        self.send_native()

        with patch("wallets.services.transaction_confirmation.sync_holding") as sync:
            with patch.object(transaction_confirmation, "_notify_wallet_users"):
                transaction_confirmation.confirm_transaction(self.tx_hash, block_number=1, wallet=self.wallet)

        self.assertEqual([call.args[1].symbol for call in sync.call_args_list], [self.native.symbol])

    def test_a_fee_larger_than_the_native_holding_floors_at_zero_rather_than_going_negative(self):
        self.send_token(fee="500")

        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("0")))
