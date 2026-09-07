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


def generate_order_cancel_message(order_uuid: str) -> str:
    return f"Cancel order {order_uuid}"


def generate_order_create_message(
    wallet_address: str,
    token_uuid: str,
    order_type: str,
    quantity: int,
    price_per_share: str,
) -> str:
    return (
        f"Create {order_type} order: "
        f"{quantity} tokens of {token_uuid} "
        f"at {price_per_share} per share "
        f"from {wallet_address}"
    )
