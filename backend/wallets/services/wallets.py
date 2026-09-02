import base64
import logging
import secrets
from hashlib import new as hashlib_new
from hashlib import sha256

import base58
import bech32
from bitcoin_message_tool import bmt
from django.conf import settings
from django.utils import timezone
from eth_account.messages import encode_defunct
from web3 import Web3

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


def generate_verification_challenge(wallet_address: str) -> str:
    nonce = secrets.token_hex(16)
    timestamp = int(timezone.now().timestamp())

    challenge = (
        f"Ledova Wallet Verification\n\n"
        f"Address: {wallet_address}\n"
        f"Timestamp: {timestamp}\n"
        f"Nonce: {nonce}\n\n"
        f"Please sign this message to verify wallet ownership.\n"
        f"This request will expire in 5 minutes."
    )

    return challenge


def verify_wallet_signature(wallet_address: str, challenge: str, signature: str, chain: str) -> bool:
    try:
        chain_upper = chain.upper()

        if chain_upper in ["ETH", "ETHEREUM", "BASE"]:
            return verify_ethereum_signature(wallet_address, challenge, signature)
        elif chain_upper in ["BTC", "BITCOIN"]:
            return verify_bitcoin_signature(wallet_address, challenge, signature)
        else:
            logger.error(f"{LoggingContext.WALLET_VERIFICATION} Unsupported chain")
            return False

    except Exception:
        logger.error(f"{LoggingContext.WALLET_VERIFICATION} Signature verification failed")
        return False


def verify_ethereum_signature(address: str, message: str, signature: str) -> bool:
    try:
        web3 = Web3()
        encoded_message = encode_defunct(text=message)
        recovered_address = web3.eth.account.recover_message(encoded_message, signature=signature)
        is_valid = recovered_address.lower() == address.lower()

        if not is_valid:
            logger.warning(f"{LoggingContext.WALLET_VERIFICATION} Ethereum signature verification failed")

        return is_valid

    except Exception:
        logger.error(f"{LoggingContext.WALLET_VERIFICATION} Ethereum signature verification error")
        return False


def verify_bitcoin_signature(address: str, message: str, signature: str) -> bool:
    try:
        network = settings.BITCOIN_NETWORK
        if not _is_allowed_bitcoin_address(address, network):
            logger.warning(f"{LoggingContext.WALLET_VERIFICATION} Bitcoin address rejected by network policy")
            return False

        signature_bytes = base64.b64decode(signature, validate=True)
        if len(signature_bytes) != 65:
            return False
        header = signature_bytes[0]

        _, recovered_pubkey, _ = bmt.verify_message(address, message, signature)
        if not recovered_pubkey:
            return False

        derived_address = _derive_bitcoin_address(bytes.fromhex(recovered_pubkey), header, network)
        is_valid = derived_address == address
        if not is_valid:
            logger.warning(f"{LoggingContext.WALLET_VERIFICATION} Bitcoin signature verification failed")
        return is_valid

    except Exception:
        logger.error(f"{LoggingContext.WALLET_VERIFICATION} Bitcoin signature verification error")
        return False


def _is_allowed_bitcoin_address(address: str, network: str) -> bool:
    if network == "test":
        return address.startswith(("m", "n", "2", "tb1"))
    if network == "regtest":
        return address.startswith("bcrt1")
    return False


def _derive_bitcoin_address(pubkey: bytes, header: int, network: str) -> str:
    pubkey_hash = hashlib_new("ripemd160", sha256(pubkey).digest()).digest()
    if 27 <= header <= 34:
        return base58.b58encode_check(b"\x6f" + pubkey_hash).decode("ascii")
    if 35 <= header <= 38:
        redeem_script = b"\x00\x14" + pubkey_hash
        script_hash = hashlib_new("ripemd160", sha256(redeem_script).digest()).digest()
        return base58.b58encode_check(b"\xc4" + script_hash).decode("ascii")
    if 39 <= header <= 42:
        hrp = "tb" if network == "test" else "bcrt"
        words = bech32.convertbits(pubkey_hash, 8, 5)
        return bech32.bech32_encode(hrp, [0] + words)
    raise ValueError("Unsupported compact Bitcoin signature header")
