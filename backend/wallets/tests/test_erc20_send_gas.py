from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from integrations.base_chain.exceptions import GasEstimationError
from integrations.blockchain.ethereum import EthereumClient
from wallets.exceptions import BlockchainAPIError
from wallets.services.transfers import prepare_erc20_transaction

FROM = "0x" + "a" * 40
TO = "0x" + "b" * 40
CONTRACT = "0x" + "c" * 40
RPC_URL = "https://base-sepolia.g.alchemy.com/v2/pR3t3nd1ngT0B3aReAlK3y"


def ethereum_client(estimate) -> EthereumClient:
    client = EthereumClient.__new__(EthereumClient)
    client.w3 = SimpleNamespace(eth=SimpleNamespace(estimate_gas=estimate))
    client.build_erc20_transfer_data = Mock(return_value="0xdata")
    return client


class AnErc20EstimateIsAnAnswerOrARefusalTest(SimpleTestCase):

    def estimate_for(self, client):
        return client.estimate_erc20_transfer_gas(
            from_address=FROM, contract_address=CONTRACT, recipient=TO, amount=Decimal("1.5"), decimals=6
        )

    def test_an_estimate_the_node_refuses_is_not_replaced_with_a_default(self):
        client = ethereum_client(Mock(side_effect=ValueError("execution reverted")))

        with self.assertRaises(GasEstimationError):
            self.estimate_for(client)

    def test_the_refusal_does_not_carry_the_node_credentials(self):
        client = ethereum_client(Mock(side_effect=ConnectionError(f"Max retries exceeded with url: {RPC_URL}")))

        with self.assertRaises(GasEstimationError) as refusal:
            self.estimate_for(client)

        self.assertNotIn("pR3t3nd1ngT0B3aReAlK3y", str(refusal.exception))
        self.assertNotIn("alchemy.com", str(refusal.exception))

    def test_an_estimate_the_node_gives_carries_headroom(self):
        client = ethereum_client(Mock(return_value=65_000))

        self.assertEqual(self.estimate_for(client), 78_000)


@patch("wallets.services.transfers.get_blockchain_client")
class ASendIsNotQuotedFromAGuessedGasLimitTest(SimpleTestCase):

    @staticmethod
    def prepare():
        return prepare_erc20_transaction(
            chain="base",
            from_address=FROM,
            to_address=TO,
            amount=Decimal("1.5"),
            token_balance=Decimal("100"),
            eth_balance=Decimal("0.0001"),
            contract_address=CONTRACT,
            token_symbol="USDC",
            token_decimals=6,
        )

    def test_a_transfer_the_node_will_not_estimate_is_refused_rather_than_priced(self, get_client):
        client = get_client.return_value
        client.estimate_erc20_transfer_gas.side_effect = GasEstimationError("the node would not estimate gas")

        with self.assertRaises(BlockchainAPIError):
            self.prepare()

        client.get_gas_price.assert_not_called()
        client.build_erc20_transfer_data.assert_not_called()

    def test_the_fee_the_caller_is_quoted_comes_from_the_estimate_the_node_gave(self, get_client):
        client = get_client.return_value
        client.estimate_erc20_transfer_gas.return_value = 78_000
        client.get_gas_price.return_value = 10**9
        client.build_erc20_transfer_data.return_value = "0xdata"
        client.get_nonce.return_value = 4
        client.w3.eth.chain_id = 84532

        prepared = prepare_erc20_transaction(
            chain="base",
            from_address=FROM,
            to_address=TO,
            amount=Decimal("1.5"),
            token_balance=Decimal("100"),
            eth_balance=Decimal("10"),
            contract_address=CONTRACT,
            token_symbol="USDC",
            token_decimals=6,
        )

        self.assertEqual(prepared["gas_limit"], 78_000)
        self.assertEqual(prepared["gas_cost_eth"], "0.000078")
