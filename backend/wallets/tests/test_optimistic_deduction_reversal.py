from decimal import Decimal
from unittest.mock import Mock, patch

from django.conf import settings
from web3 import Web3

from assets.services.identity import native_asset_for_chain
from wallets.models import Holding, Transaction
from wallets.services import transaction_confirmation, transfers
from wallets.tests.test_broadcast_transfer_guard import (
    RECIPIENT,
    USDC_CONTRACT,
    BroadcastTransferGuardTestCase,
    erc20_transfer_data,
    sign,
)

FEE = "0.002"


@patch.object(transfers, "_schedule_confirmation_checks")
@patch("wallets.services.submissions.get_blockchain_client")
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

    def record_acknowledgement(self, get_client, signed):
        self.tx_hash = Web3.keccak(hexstr=signed).to_0x_hex()
        get_client.return_value.assert_expected_chain = Mock(return_value=settings.BLOCKCHAIN_CHAIN_ID)
        get_client.return_value.get_transaction_receipt.return_value = None
        get_client.return_value.broadcast_transaction.return_value = self.tx_hash

    def send_token(self, get_client, amount="1.5", raw=1_500_000, fee=FEE):
        signed = sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, raw), gas=int(Decimal(fee) * 10**9))
        self.record_acknowledgement(get_client, signed)
        return self.broadcast(
            signed_transaction=signed,
            to_address=RECIPIENT,
            amount=amount,
            token_contract=USDC_CONTRACT,
            transaction_fee=fee,
        )

    def send_native(self, get_client, amount="0.25", value=25 * 10**16, fee=FEE):
        signed = sign(to=RECIPIENT, value=value, gas=int(Decimal(fee) * 10**9))
        self.record_acknowledgement(get_client, signed)
        return self.broadcast(
            signed_transaction=signed,
            to_address=RECIPIENT,
            amount=amount,
            transaction_fee=fee,
        )

    def fail_transfer(self, tx_hash):
        with patch.object(transaction_confirmation, "_notify_wallet_users"):
            return transaction_confirmation.fail_transaction(tx_hash, reason="reverted", wallet=self.wallet)

    def test_a_wallet_with_no_native_holding_is_not_given_one_by_a_failed_transfer(self, get_client, schedule):
        self.hold(self.token, "100")

        self.assertEqual(self.send_token(get_client).status_code, 200)
        self.assertEqual(self.quantity(self.native), Decimal("0"))
        self.fail_transfer(self.tx_hash)

        self.assertEqual(self.quantity(self.native), Decimal("0"))
        self.assertEqual(self.quantity(self.token), Decimal("100"))

    def test_a_transfer_larger_than_the_holding_comes_back_to_where_it_started(self, get_client, schedule):
        self.hold(self.token, "1")
        self.hold(self.native, "5")

        self.assertEqual(self.send_token(get_client).status_code, 200)
        self.assertEqual(self.quantity(self.token), Decimal("0"))
        self.fail_transfer(self.tx_hash)

        self.assertEqual(self.quantity(self.token), Decimal("1"))
        self.assertEqual(self.quantity(self.native), Decimal("5"))

    def test_a_fee_larger_than_the_native_holding_comes_back_to_where_it_started(self, get_client, schedule):
        self.hold(self.token, "100")
        self.hold(self.native, "5")

        self.assertEqual(self.send_token(get_client, fee="500").status_code, 200)
        self.assertEqual(self.quantity(self.native), Decimal("0"))
        self.fail_transfer(self.tx_hash)

        self.assertEqual(self.quantity(self.native), Decimal("5"))
        self.assertEqual(self.quantity(self.token), Decimal("100"))

    def test_a_native_send_larger_than_the_one_holding_comes_back_to_where_it_started(self, get_client, schedule):
        self.hold(self.native, "0.1")

        self.assertEqual(self.send_native(get_client).status_code, 200)
        self.assertEqual(self.quantity(self.native), Decimal("0"))
        self.fail_transfer(self.tx_hash)

        self.assertEqual(self.quantity(self.native), Decimal("0.1"))

    def test_an_unclamped_transfer_still_comes_back_in_full(self, get_client, schedule):
        self.hold(self.token, "100")
        self.hold(self.native, "5")

        self.assertEqual(self.send_token(get_client).status_code, 200)
        self.assertEqual((self.quantity(self.token), self.quantity(self.native)), (Decimal("98.5"), Decimal("4.998")))
        self.fail_transfer(self.tx_hash)

        self.assertEqual((self.quantity(self.token), self.quantity(self.native)), (Decimal("100"), Decimal("5")))

    def test_the_row_records_what_each_holding_actually_gave_up(self, get_client, schedule):
        self.hold(self.token, "100")
        self.hold(self.native, "5")
        self.send_token(get_client, fee="500")

        tx = Transaction.objects.get(tx_hash=self.tx_hash)

        self.assertEqual(tx.deducted_amount, Decimal("1.5"))
        self.assertEqual(tx.deducted_fee, Decimal("5"))
        self.assertEqual(tx.transaction_fee_estimated, Decimal("500"))

    def test_a_native_send_records_one_deduction_and_no_separate_fee(self, get_client, schedule):
        self.hold(self.native, "5")
        self.send_native(get_client)

        tx = Transaction.objects.get(tx_hash=self.tx_hash)

        self.assertEqual(tx.deducted_amount, Decimal("0.252"))
        self.assertIsNone(tx.deducted_fee)

    def test_a_row_without_a_record_cannot_guess_a_refund_during_a_provider_outage(self, get_client, schedule):
        self.hold(self.token, "100")
        self.hold(self.native, "5")
        self.send_token(get_client)
        Transaction.objects.filter(tx_hash=self.tx_hash).update(deducted_amount=None, deducted_fee=None)

        with patch("wallets.services.holdings.fetch_chain_balance", return_value=None):
            self.fail_transfer(self.tx_hash)

        self.assertEqual((self.quantity(self.token), self.quantity(self.native)), (Decimal("98.5"), Decimal("4.998")))
