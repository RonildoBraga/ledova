import os

from ledova_backend.chain_safety import parse_bitcoin_network, parse_evm_chain_id
from ledova_backend.environment import read_bool
from ledova_backend.settings.integrations import ALCHEMY_BASE_URL

BLOCKCHAIN_RPC_URL = os.environ.get("BLOCKCHAIN_RPC_URL", ALCHEMY_BASE_URL or "http://localhost:8545")
BLOCKCHAIN_CHAIN_ID = parse_evm_chain_id(os.environ.get("BLOCKCHAIN_CHAIN_ID", "84532"), "BLOCKCHAIN_CHAIN_ID")
ETHEREUM_CHAIN_ID = parse_evm_chain_id(os.environ.get("ETHEREUM_CHAIN_ID", "11155111"), "ETHEREUM_CHAIN_ID")
BITCOIN_NETWORK = parse_bitcoin_network(os.environ.get("BITCOIN_NETWORK", "test"))
EVM_ASSET_TRANSFER_HISTORY_ENABLED = read_bool("EVM_ASSET_TRANSFER_HISTORY_ENABLED", default=False)

BLOCKCHAIN_OPERATOR_KEY = os.environ.get("BLOCKCHAIN_OPERATOR_KEY", "")
BLOCKCHAIN_OPERATOR_ADDRESS = os.environ.get("BLOCKCHAIN_OPERATOR_ADDRESS", "")

WHITELIST_CONTRACT_ADDRESS = os.environ.get("WHITELIST_CONTRACT_ADDRESS", "")
SHARE_TOKEN_FACTORY_ADDRESS = os.environ.get("SHARE_TOKEN_FACTORY_ADDRESS", "")
ATOMIC_SWAP_ADDRESS = os.environ.get("ATOMIC_SWAP_ADDRESS", "")
STABLECOIN_CONTRACT_ADDRESS = os.environ.get("STABLECOIN_CONTRACT_ADDRESS", "")
YIELD_TOKEN_CONTRACT_ADDRESS = os.environ.get("YIELD_TOKEN_CONTRACT_ADDRESS", "")
TOKEN_DEPLOYMENT_CHAIN = os.environ.get("TOKEN_DEPLOYMENT_CHAIN", "").strip().lower()

SWAP_ORDER_EXPIRY_HOURS = int(os.environ.get("SWAP_ORDER_EXPIRY_HOURS", "24"))
