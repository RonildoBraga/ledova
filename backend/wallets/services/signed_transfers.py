from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Optional, Tuple

from django.conf import settings
from eth_utils import from_wei
from web3 import Web3

from shared.constants import (
    BLOCKCHAIN_BASE,
    BLOCKCHAIN_ETHEREUM,
    EVM_BLOCKCHAINS,
    SUPPORTED_CHAINS,
    normalize_chain,
)
from wallets.exceptions import InvalidTransactionException, UnsupportedChainException

ERC20_TRANSFER_SELECTOR = bytes.fromhex("a9059cbb")
ERC20_TRANSFER_DATA_LENGTH = 68
ADDRESS_PADDING = 12
DEFAULT_TOKEN_DECIMALS = 18

CHAIN_ID_SETTING = {
    BLOCKCHAIN_ETHEREUM: "ETHEREUM_CHAIN_ID",
    BLOCKCHAIN_BASE: "BLOCKCHAIN_CHAIN_ID",
}

UNDECODABLE = "The signed transaction could not be decoded."
WRONG_NETWORK = "The signed transaction is for chain {actual}, not chain {expected}."
UNSIGNED_NETWORK = "The signed transaction does not name a chain, so it could be replayed on another one."
CONTRACT_CREATION = "Contract creation cannot be broadcast through a wallet transfer."
UNSUPPORTED_PAYLOAD = "Only a native transfer or an ERC-20 transfer call can be broadcast through this wallet."
MALFORMED_RECIPIENT = "The ERC-20 recipient argument is malformed."


@dataclass(frozen=True)
class SignedTransferPlan:
    to_address: str
    amount: Decimal
    token_contract: Optional[str]


def expected_chain_id(chain: str) -> int:
    setting = CHAIN_ID_SETTING.get(normalize_chain(chain))
    if setting is None:
        raise UnsupportedChainException(chain.upper())
    return getattr(settings, setting)


def plan_signed_transfer(
    wallet, signed_transaction: str, declared_token_contract: Optional[str] = None
) -> Optional[SignedTransferPlan]:
    from wallets.services.transaction_confirmation import TransactionConfirmationService

    chain = normalize_chain(wallet.chain)

    if chain not in SUPPORTED_CHAINS:
        raise UnsupportedChainException(wallet.chain.upper())

    if declared_token_contract:
        TransactionConfirmationService.resolve_transfer_asset(wallet, declared_token_contract)

    if chain not in EVM_BLOCKCHAINS:
        return None

    return _evm_plan(wallet, signed_transaction)


def _evm_plan(wallet, signed_transaction: str) -> SignedTransferPlan:
    from tokens.models import ShareToken
    from wallets.services.transaction_confirmation import (
        NOT_TRANSFERABLE,
        TransactionConfirmationService,
    )

    decoded = _decode(signed_transaction)
    expected = expected_chain_id(wallet.chain)

    if decoded.chain_id is None:
        raise InvalidTransactionException(UNSIGNED_NETWORK)

    if decoded.chain_id != expected:
        raise InvalidTransactionException(WRONG_NETWORK.format(actual=decoded.chain_id, expected=expected))

    if decoded.to is None:
        raise InvalidTransactionException(CONTRACT_CREATION)

    share_token = ShareToken.objects.filter(contract_address__iexact=decoded.to).first()
    if share_token is not None:
        raise InvalidTransactionException(NOT_TRANSFERABLE.format(symbol=share_token.symbol))

    if not decoded.data:
        return SignedTransferPlan(
            to_address=decoded.to,
            amount=Decimal(from_wei(decoded.value, "ether")),
            token_contract=None,
        )

    recipient, raw_amount = _erc20_transfer_arguments(decoded.data)
    asset = TransactionConfirmationService.resolve_transfer_asset(wallet, decoded.to)
    decimals = asset.decimals if asset.decimals is not None else DEFAULT_TOKEN_DECIMALS

    return SignedTransferPlan(
        to_address=recipient,
        amount=_scaled(raw_amount, decimals),
        token_contract=decoded.to,
    )


def _decode(signed_transaction: str):
    from tokens.services.signed_transactions import decode_signed_transaction

    raw = signed_transaction[2:] if signed_transaction.startswith("0x") else signed_transaction

    try:
        return decode_signed_transaction(bytes.fromhex(raw))
    except ValueError:
        raise InvalidTransactionException(UNDECODABLE)


def _erc20_transfer_arguments(data: bytes) -> Tuple[str, int]:
    if len(data) != ERC20_TRANSFER_DATA_LENGTH or data[:4] != ERC20_TRANSFER_SELECTOR:
        raise InvalidTransactionException(UNSUPPORTED_PAYLOAD)

    recipient_word = data[4:36]
    if any(recipient_word[:ADDRESS_PADDING]):
        raise InvalidTransactionException(MALFORMED_RECIPIENT)

    return Web3.to_checksum_address(recipient_word[ADDRESS_PADDING:]), int.from_bytes(data[36:68], "big")


def _scaled(raw_amount: int, decimals: int) -> Decimal:
    with localcontext() as context:
        context.prec = len(str(raw_amount)) + decimals + 1
        return Decimal(raw_amount).scaleb(-decimals)
