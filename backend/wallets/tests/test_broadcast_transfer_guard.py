from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from eth_account import Account
from rest_framework.test import APITestCase
from web3 import Web3

from assets.models import Asset, AssetChainDeployment
from assets.services.identity import native_asset_for_chain
from companies.models import Company, CompanyType
from tokens.models import ShareToken, ShareTokenStatus
from users.models import UserAccount, UserProfile
from wallets.models import Holding, Transaction, Wallet
from wallets.services.signed_transfers import (
    AMOUNT_OUT_OF_RANGE,
    AMOUNT_TOO_PRECISE,
    CONTRACT_CREATION,
    ERC20_CARRIES_VALUE,
    SIGNER_MISMATCH,
    UNDECODABLE,
    UNSUPPORTED_ENVELOPE,
    UNSUPPORTED_PAYLOAD,
    WRONG_NETWORK,
)
from wallets.services.transaction_confirmation import NOT_TRANSFERABLE
from wallets.services.transfers import TransferService

SIGNER = Account.from_key("0x" + "42" * 32)
WALLET_ADDRESS = SIGNER.address
RECIPIENT = Web3.to_checksum_address("0x" + "b" * 40)
LIAR = Web3.to_checksum_address("0x" + "d" * 40)
USDC_CONTRACT = Web3.to_checksum_address("0x" + "c" * 40)
SHARE_CONTRACT = Web3.to_checksum_address("0x" + "5e" * 20)
BITCOIN_ADDRESS = "tb1qsenderwallet"
BITCOIN_RECIPIENT = "tb1qrecipient"
ERC20_TRANSFER_SELECTOR = "a9059cbb"


def sign(to=None, value=0, data=b"", chain_id=None, nonce=0):
    fields = {
        "nonce": nonce,
        "value": value,
        "gas": 90000,
        "gasPrice": 10**9,
        "chainId": settings.BLOCKCHAIN_CHAIN_ID if chain_id is None else chain_id,
        "data": data,
    }
    if to is not None:
        fields["to"] = to
    return SIGNER.sign_transaction(fields).raw_transaction.to_0x_hex()


def sign_set_code(to=None, nonce=0):
    authorization = SIGNER.sign_authorization(
        {"chainId": settings.BLOCKCHAIN_CHAIN_ID, "address": SIGNER.address, "nonce": nonce + 1}
    )
    fields = {
        "nonce": nonce,
        "value": 0,
        "gas": 200000,
        "maxFeePerGas": 10**9,
        "maxPriorityFeePerGas": 10**9,
        "chainId": settings.BLOCKCHAIN_CHAIN_ID,
        "data": b"",
        "type": 4,
        "accessList": [],
        "authorizationList": [authorization],
        "to": SIGNER.address if to is None else to,
    }
    return SIGNER.sign_transaction(fields).raw_transaction.to_0x_hex()


def erc20_transfer_data(recipient, raw_amount):
    return (
        bytes.fromhex(ERC20_TRANSFER_SELECTOR)
        + bytes(12)
        + bytes.fromhex(recipient[2:])
        + int(raw_amount).to_bytes(32, "big")
    )


class BroadcastTransferGuardTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

        self.user = get_user_model().objects.create_user(email="broadcast@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=self.user)
        self.account = UserAccount.objects.create(account_number="BROADCAST")
        self.account.user_profiles.add(profile)
        self.wallet = Wallet.objects.create(
            user_account=self.account, address=WALLET_ADDRESS, chain="base", verification_status="VERIFIED"
        )
        self.client.force_authenticate(self.user)

    def broadcast(self, wallet=None, **payload):
        wallet = wallet or self.wallet
        return self.client.post(f"/api/wallets/{wallet.uuid}/broadcast-transfer/", payload)

    def bitcoin_wallet(self):
        return Wallet.objects.create(
            user_account=self.account,
            address=BITCOIN_ADDRESS,
            chain="bitcoin",
            verification_status="VERIFIED",
        )

    def usdc(self):
        asset = Asset.objects.create(
            symbol="USDC", name="USD Coin", asset_type="erc20_token", decimals=6, is_verified=True
        )
        AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address=USDC_CONTRACT, decimals=6)
        return asset

    def wide_decimal_asset(self):
        asset = Asset.objects.create(
            symbol="WIDE", name="Wide Decimals", asset_type="erc20_token", decimals=30, is_verified=True
        )
        AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address=USDC_CONTRACT, decimals=30)
        return asset

    def usdc_with_disagreeing_decimals(self):
        asset = Asset.objects.create(
            symbol="USDT", name="Tether", asset_type="erc20_token", decimals=18, is_verified=True
        )
        AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address=USDC_CONTRACT, decimals=6)
        return asset

    def share_token(self):
        company = Company.objects.create(
            owner=self.user, name="Acme Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="000000123"
        )
        return ShareToken.objects.create(
            company=company,
            name="Acme Ordinary",
            symbol="ORD",
            total_supply="1000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address=SHARE_CONTRACT,
            chain="base",
        )


@patch.object(TransferService, "_schedule_confirmation_checks")
@patch("wallets.services.transfers.get_blockchain_client")
class BroadcastTransferRefusalTest(BroadcastTransferGuardTestCase):
    def test_a_share_token_transfer_is_refused_when_the_caller_omits_the_contract_field(self, get_client, schedule):
        token = self.share_token()

        response = self.broadcast(
            signed_transaction=sign(to=SHARE_CONTRACT, data=erc20_transfer_data(RECIPIENT, 1)),
            to_address=RECIPIENT,
            amount="1",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], NOT_TRANSFERABLE.format(symbol=token.symbol))
        get_client.assert_not_called()
        schedule.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())

    def test_a_set_code_transaction_is_refused_rather_than_read_as_a_zero_value_send(self, get_client, schedule):
        response = self.broadcast(signed_transaction=sign_set_code(), to_address=SIGNER.address, amount="0")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], UNSUPPORTED_ENVELOPE)
        get_client.assert_not_called()
        schedule.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())

    def test_a_transaction_signed_by_another_key_is_refused(self, get_client, schedule):
        stranger = Account.from_key("0x" + "11" * 32)
        fields = {
            "nonce": 0,
            "value": 10**17,
            "gas": 90000,
            "gasPrice": 10**9,
            "chainId": settings.BLOCKCHAIN_CHAIN_ID,
            "data": b"",
            "to": RECIPIENT,
        }
        signed = stranger.sign_transaction(fields).raw_transaction.to_0x_hex()

        response = self.broadcast(signed_transaction=signed, to_address=RECIPIENT, amount="0.1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], SIGNER_MISMATCH.format(signer=stranger.address))
        get_client.assert_not_called()
        schedule.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())

    def test_an_erc20_amount_finer_than_the_column_is_refused_rather_than_recorded_as_zero(self, get_client, schedule):
        self.wide_decimal_asset()

        response = self.broadcast(
            signed_transaction=sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, 2_500_000)),
            to_address=RECIPIENT,
            amount="1",
            token_contract=USDC_CONTRACT,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], AMOUNT_TOO_PRECISE)
        get_client.assert_not_called()
        schedule.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())

    def test_an_erc20_amount_too_large_to_record_is_refused_before_the_broadcast(self, get_client, schedule):
        self.usdc()

        response = self.broadcast(
            signed_transaction=sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, 2**256 - 1)),
            to_address=RECIPIENT,
            amount="1",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], AMOUNT_OUT_OF_RANGE)
        get_client.assert_not_called()
        schedule.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())

    def test_a_transaction_signed_for_another_network_is_refused(self, get_client, schedule):
        other_chain = settings.BLOCKCHAIN_CHAIN_ID + 1

        response = self.broadcast(signed_transaction=sign(to=RECIPIENT, value=10**17, chain_id=other_chain))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            WRONG_NETWORK.format(actual=other_chain, expected=settings.BLOCKCHAIN_CHAIN_ID),
        )
        get_client.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())

    def test_a_contract_creation_transaction_is_refused(self, get_client, schedule):
        response = self.broadcast(signed_transaction=sign(value=1, data=bytes.fromhex("60806040")))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], CONTRACT_CREATION)
        get_client.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())

    def test_an_arbitrary_contract_call_is_refused(self, get_client, schedule):
        self.usdc()

        response = self.broadcast(signed_transaction=sign(to=USDC_CONTRACT, data=bytes.fromhex("095ea7b3" + "00" * 64)))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], UNSUPPORTED_PAYLOAD)
        get_client.assert_not_called()

    def test_erc20_calldata_carrying_native_value_is_refused(self, get_client, schedule):
        self.usdc()
        native = native_asset_for_chain("base")
        Holding.objects.create(wallet=self.wallet, asset=native, quantity=Decimal("10"))

        response = self.broadcast(
            signed_transaction=sign(to=USDC_CONTRACT, value=9 * 10**18, data=erc20_transfer_data(RECIPIENT, 1)),
            to_address=RECIPIENT,
            amount="0.000001",
            token_contract=USDC_CONTRACT,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], ERC20_CARRIES_VALUE)
        get_client.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())
        self.assertEqual(Holding.objects.get(wallet=self.wallet, asset=native).quantity, Decimal("10"))

    def test_a_negative_transaction_fee_is_refused_before_it_credits_the_holding(self, get_client, schedule):
        native = native_asset_for_chain("base")

        response = self.broadcast(
            signed_transaction=sign(to=RECIPIENT, value=1),
            to_address=RECIPIENT,
            amount="0.000000000000000001",
            transaction_fee="-1000000",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("transactionFee", response.json())
        get_client.assert_not_called()
        self.assertFalse(Holding.objects.filter(wallet=self.wallet, asset=native).exists())

    def test_a_negative_bitcoin_amount_is_refused_before_it_credits_the_holding(self, get_client, schedule):
        wallet = self.bitcoin_wallet()
        native = native_asset_for_chain("bitcoin")

        response = self.broadcast(
            wallet=wallet,
            signed_transaction="0200000001deadbeef",
            to_address=BITCOIN_RECIPIENT,
            amount="-500000",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.json())
        get_client.assert_not_called()
        self.assertFalse(Holding.objects.filter(wallet=wallet, asset=native).exists())

    def test_an_undecodable_signed_transaction_is_refused(self, get_client, schedule):
        response = self.broadcast(signed_transaction="0x02f8" + "0" * 60)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], UNDECODABLE)
        get_client.assert_not_called()


@patch.object(TransferService, "_schedule_confirmation_checks")
@patch("wallets.services.transfers.get_blockchain_client")
class BroadcastTransferRecordingTest(BroadcastTransferGuardTestCase):
    def test_an_ordinary_native_send_still_broadcasts(self, get_client, schedule):
        get_client.return_value.broadcast_transaction.return_value = "0xnative"

        response = self.broadcast(
            signed_transaction=sign(to=RECIPIENT, value=25 * 10**16),
            to_address=RECIPIENT,
            amount="0.25",
            transaction_fee="0.000021",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["txHash"], "0xnative")

        recorded = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual(recorded.to_address, RECIPIENT)
        self.assertEqual(recorded.amount, Decimal("0.25"))
        self.assertEqual(recorded.asset.symbol, "ETH")

    def test_an_erc20_amount_is_scaled_by_the_deployment_not_the_asset(self, get_client, schedule):
        self.usdc_with_disagreeing_decimals()
        get_client.return_value.broadcast_transaction.return_value = "0xdecimals"

        response = self.broadcast(
            signed_transaction=sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, 2_500_000)),
            to_address=RECIPIENT,
            amount="1",
            token_contract=USDC_CONTRACT,
        )

        self.assertEqual(response.status_code, 200)
        recorded = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual(recorded.amount, Decimal("2.5"))

    def test_an_ordinary_erc20_send_still_broadcasts(self, get_client, schedule):
        self.usdc()
        get_client.return_value.broadcast_transaction.return_value = "0xerc20"

        response = self.broadcast(
            signed_transaction=sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, 1_500_000)),
            to_address=RECIPIENT,
            amount="1.5",
            token_contract=USDC_CONTRACT,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["txHash"], "0xerc20")

        recorded = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual(recorded.to_address, RECIPIENT)
        self.assertEqual(recorded.amount, Decimal("1.5"))
        self.assertEqual(recorded.asset.symbol, "USDC")

    def test_an_ordinary_bitcoin_send_still_broadcasts(self, get_client, schedule):
        wallet = self.bitcoin_wallet()
        get_client.return_value.broadcast_transaction.return_value = "btc-hash"

        response = self.broadcast(
            wallet=wallet,
            signed_transaction="0200000001deadbeef",
            to_address=BITCOIN_RECIPIENT,
            amount="0.001",
            transaction_fee="0.00001",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["txHash"], "btc-hash")

        recorded = Transaction.objects.get(wallet=wallet)
        self.assertEqual((recorded.to_address, recorded.amount), (BITCOIN_RECIPIENT, Decimal("0.001")))
        self.assertEqual(recorded.asset.symbol, "BTC")

    def test_the_recorded_row_follows_the_signed_transaction_not_the_body(self, get_client, schedule):
        get_client.return_value.broadcast_transaction.return_value = "0xhonest"

        response = self.broadcast(
            signed_transaction=sign(to=RECIPIENT, value=25 * 10**16),
            to_address=LIAR,
            amount="99",
        )

        self.assertEqual(response.status_code, 200)

        recorded = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual((recorded.to_address, recorded.amount), (RECIPIENT, Decimal("0.25")))

    def test_an_erc20_row_follows_the_signed_amount_not_the_body(self, get_client, schedule):
        self.usdc()
        get_client.return_value.broadcast_transaction.return_value = "0xhonest-erc20"

        response = self.broadcast(
            signed_transaction=sign(to=USDC_CONTRACT, data=erc20_transfer_data(RECIPIENT, 1_500_000)),
            to_address=LIAR,
            amount="9999",
            token_contract=USDC_CONTRACT,
        )

        self.assertEqual(response.status_code, 200)

        recorded = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual((recorded.to_address, recorded.amount), (RECIPIENT, Decimal("1.5")))
        self.assertEqual(recorded.asset.symbol, "USDC")


class BroadcastTransferThrottleTest(BroadcastTransferGuardTestCase):
    @patch("wallets.views.wallet.TransferService")
    def test_the_route_allows_ten_broadcasts_a_minute(self, transfer_service):
        transfer_service.broadcast_transfer.return_value = {"success": True}

        statuses = [
            self.broadcast(signed_transaction=sign(to=RECIPIENT, value=1, nonce=nonce)).status_code
            for nonce in range(11)
        ]

        self.assertEqual(statuses, [200] * 10 + [429])
        self.assertEqual(transfer_service.broadcast_transfer.call_count, 10)
