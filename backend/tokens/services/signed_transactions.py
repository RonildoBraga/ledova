from dataclasses import dataclass
from typing import Optional

from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction as LegacyTransaction
from eth_account.typed_transactions import TypedTransaction
from eth_utils import to_checksum_address
from hexbytes import HexBytes

TYPED_ENVELOPE_MAX_PREFIX = 0x7F  # EIP-2718 envelope byte 0x00..0x7f; a legacy RLP list starts at 0xc0


@dataclass(frozen=True)
class DecodedSignedTransaction:
    sender: str
    to: Optional[str]  # checksum address; None for contract creation
    chain_id: Optional[int]  # None for a pre-EIP-155 legacy transaction
    value: int
    data: bytes


def decode_signed_transaction(raw_transaction: bytes) -> DecodedSignedTransaction:
    """Decode a signed legacy or typed transaction and recover its sender; ValueError when the bytes are not one."""
    if not raw_transaction:
        raise ValueError("Empty transaction")

    try:
        if raw_transaction[0] <= TYPED_ENVELOPE_MAX_PREFIX:
            fields = TypedTransaction.from_bytes(HexBytes(raw_transaction)).as_dict()
            chain_id: Optional[int] = int(fields["chainId"])
        else:
            fields = LegacyTransaction.from_bytes(raw_transaction).as_dict()
            chain_id = _legacy_chain_id(int(fields["v"]))
        sender = Account.recover_transaction(raw_transaction)
    except Exception as exc:  # rlp, eth_account and eth_keys raise their own decoding and validation errors
        raise ValueError("Unable to decode signed transaction") from exc

    to = bytes(fields.get("to") or b"")
    return DecodedSignedTransaction(
        sender=sender,
        to=to_checksum_address(to) if to else None,
        chain_id=chain_id,
        value=int(fields.get("value") or 0),
        data=bytes(fields.get("data") or b""),
    )


def _legacy_chain_id(v: int) -> Optional[int]:
    if v in (27, 28):
        return None
    return (v - 35) // 2
