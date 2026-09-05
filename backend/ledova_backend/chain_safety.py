from django.core.exceptions import ImproperlyConfigured

SUPPORTED_EVM_CHAIN_IDS = frozenset({1337, 31337, 84532, 11155111})
SUPPORTED_BITCOIN_NETWORKS = frozenset({"regtest", "test"})


def parse_evm_chain_id(value: str, setting_name: str) -> int:
    try:
        chain_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(f"{setting_name} must be an integer chain ID") from exc

    if chain_id not in SUPPORTED_EVM_CHAIN_IDS:
        raise ImproperlyConfigured(f"{setting_name}={chain_id} is not a supported local or public-testnet chain ID")
    return chain_id


def parse_bitcoin_network(value: str) -> str:
    network = value.strip().lower()
    if network not in SUPPORTED_BITCOIN_NETWORKS:
        raise ImproperlyConfigured("BITCOIN_NETWORK must be 'test' or 'regtest'")
    return network
