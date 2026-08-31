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


def generate_order_modify_message(
    order_uuid: str,
    token_symbol: str,
    order_type: str,
    new_quantity: int,
    new_min_quantity: int,
    new_price_per_share: str,
    wallet_address: str,
    nonce: int,
) -> str:
    return (
        f"Modify Order\n"
        f"Order: {order_uuid}\n"
        f"Token: {token_symbol}\n"
        f"Type: {order_type}\n"
        f"New Quantity: {new_quantity}\n"
        f"New Min Quantity: {new_min_quantity}\n"
        f"New Price: {new_price_per_share} AUDY\n"
        f"Wallet: {wallet_address}\n"
        f"Nonce: {nonce}"
    )


def parse_order_modify_message(message: str) -> dict:
    lines = message.strip().split("\n")
    data = {}

    key_map = {
        "Order:": "order_uuid",
        "Token:": "token_symbol",
        "Type:": "order_type",
        "New Quantity:": "new_quantity",
        "New Min Quantity:": "new_min_quantity",
        "New Price:": "new_price_per_share",
        "Wallet:": "wallet_address",
        "Nonce:": "nonce",
    }

    for line in lines:
        for prefix, key in key_map.items():
            if line.startswith(prefix):
                value = line[len(prefix) :].strip()
                if key == "new_price_per_share" and value.endswith(" AUDY"):
                    value = value[:-5]
                data[key] = value
                break

    if "new_quantity" in data:
        data["new_quantity"] = int(data["new_quantity"])
    if "new_min_quantity" in data:
        data["new_min_quantity"] = int(data["new_min_quantity"])
    if "nonce" in data:
        data["nonce"] = int(data["nonce"])

    return data
