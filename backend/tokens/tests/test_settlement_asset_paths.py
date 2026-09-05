from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from assets.models import AssetChainDeployment
from operators.models import Operator, ReceivingChain
from shared.tests.tenants import make_tenant
from tokens.filters import TransferOrderFilter
from tokens.models import TransferOrder
from tokens.serializers import PrepareTransferSerializer
from tokens.services.atomic_swap_service import AtomicSwapService, payment_address
from tokens.services.transfer_service import TransferService

BASE_ADDRESS = "0x" + "5" * 40
ETHEREUM_ADDRESS = "0x" + "e" * 40
RECIPIENT = "0x" + "d" * 40


class SwapSettlementAddressTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("alice")
        self.asset = self.tenant.refs.stablecoin
        AssetChainDeployment.objects.create(
            asset=self.asset, chain="ethereum", contract_address=ETHEREUM_ADDRESS, decimals=2
        )

    def test_the_swap_payment_address_follows_the_receiving_chain(self):
        self.assertEqual(self.asset.contract_address, BASE_ADDRESS)
        self.assertEqual(payment_address(self.tenant.swap), BASE_ADDRESS)

        operator = Operator.get()
        operator.receiving_wallet_chain = ReceivingChain.ETHEREUM
        operator.save(update_fields=["receiving_wallet_chain"])

        self.assertEqual(payment_address(self.tenant.swap), ETHEREUM_ADDRESS)

    @patch("whitelist.services.whitelist.get_base_chain_client")
    @patch("tokens.services.atomic_swap_service.get_base_chain_client")
    def test_a_matched_pair_creates_a_swap_priced_in_the_settlement_asset_units(self, chain_client, _whitelist):
        chain_client.return_value = MagicMock(
            chain_id=31337, to_checksum_address=lambda address: address.replace("0X", "0x")
        )
        service = AtomicSwapService()

        with patch.object(AtomicSwapService, "contract_address", RECIPIENT):
            swap = service.create_swap_order(
                sell_order=self.tenant.order,
                buy_order=self.tenant.counter_order,
                share_amount=4,
                price_per_share=Decimal("1.50"),
            )

        self.assertEqual(swap.payment_asset, self.asset)
        self.assertEqual(swap.payment_amount, 600)


class TransferOrderFilterTest(TestCase):
    def test_orders_can_be_filtered_by_their_settlement_asset(self):
        tenant = make_tenant("alice")
        filtered = TransferOrderFilter(
            {"payment_asset": str(tenant.refs.stablecoin.uuid)}, queryset=TransferOrder.objects.all()
        )

        self.assertEqual(filtered.qs.count(), 2)
        self.assertEqual(
            TransferOrderFilter({"payment_asset": str(uuid4())}, queryset=TransferOrder.objects.all()).qs.count(), 0
        )


class TransferSettlementAddressTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("alice")
        self.asset = self.tenant.refs.stablecoin

    def test_the_contract_address_comes_from_the_receiving_chain_deployment(self):
        AssetChainDeployment.objects.create(
            asset=self.asset, chain="ethereum", contract_address=ETHEREUM_ADDRESS, decimals=2
        )

        self.assertEqual(TransferService.contract_address(self.asset), BASE_ADDRESS)
        self.assertEqual(
            TransferService.contract_address(self.tenant.deployed_token),
            self.tenant.deployed_token.contract_address,
        )

        AssetChainDeployment.objects.filter(asset=self.asset, chain="base").update(is_active=False)
        self.assertEqual(TransferService.contract_address(self.asset), "")

    def test_prepare_transfer_accepts_a_supported_settlement_asset_only(self):
        payload = {
            "token": str(self.asset.uuid),
            "from_address": "0x" + "a" * 40,
            "to_address": RECIPIENT,
            "amount": 100,
        }

        unsupported = PrepareTransferSerializer(data=payload)
        self.assertFalse(unsupported.is_valid())
        self.assertEqual(unsupported.errors["token"], ["Settlement asset is not available on the settlement chain"])

        Operator.get().supported_settlement_assets.add(self.asset)
        supported = PrepareTransferSerializer(data=payload)
        self.assertTrue(supported.is_valid(), supported.errors)
        self.assertEqual(supported.validated_data["token"], self.asset)

        share_token = PrepareTransferSerializer(data={**payload, "token": str(self.tenant.deployed_token.uuid)})
        self.assertTrue(share_token.is_valid(), share_token.errors)
        self.assertEqual(share_token.validated_data["token"], self.tenant.deployed_token)
