import logging
from typing import Optional

from eth_account import Account
from eth_account.messages import encode_defunct

logger = logging.getLogger(__name__)


def recover_address_from_signature(message: str, signature: str) -> Optional[str]:
    try:
        message_hash = encode_defunct(text=message)
        recovered = Account.recover_message(message_hash, signature=signature)
        return recovered
    except Exception as e:
        logger.warning(f"Signature recovery failed: {e}")
        return None


def verify_signature(message: str, signature: str, expected_address: str) -> bool:
    recovered = recover_address_from_signature(message, signature)
    if not recovered:
        return False
    return recovered.lower() == expected_address.lower()
