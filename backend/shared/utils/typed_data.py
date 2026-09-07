from typing import Optional

from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_typed_data
from eth_utils import to_checksum_address

DOMAIN_NAME = "Ledova Trading"
DOMAIN_VERSION = "1"

ZERO_ADDRESS = "0x" + "0" * 40


def build_domain(chain_id: int, verifying_contract: Optional[str]) -> dict:
    return {
        "name": DOMAIN_NAME,
        "version": DOMAIN_VERSION,
        "chainId": int(chain_id),
        "verifyingContract": to_checksum_address(verifying_contract or ZERO_ADDRESS),
    }


def signable_message(domain: dict, types: dict, message: dict):
    return encode_typed_data(domain_data=domain, message_types=types, message_data=message)


def typed_data_digest(domain: dict, types: dict, message: dict) -> str:
    return "0x" + _hash_eip191_message(signable_message(domain, types, message)).hex().removeprefix("0x")


def recover_typed_data_signer(domain: dict, types: dict, message: dict, signature: str) -> Optional[str]:
    try:
        return Account.recover_message(signable_message(domain, types, message), signature=signature)
    except Exception:
        return None
