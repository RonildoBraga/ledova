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
from wallets.services.chain import token_deployment_decimals

ERC20_TRANSFER_SELECTOR = bytes.fromhex("a9059cbb")
ERC20_TRANSFER_DATA_LENGTH = 68
ADDRESS_PADDING = 12
AMOUNT_MAX_DIGITS = 30
AMOUNT_DECIMAL_PLACES = 18
AMOUNT_LIMIT = Decimal(10) ** (AMOUNT_MAX_DIGITS - AMOUNT_DECIMAL_PLACES)
AMOUNT_QUANTUM = Decimal(1).scaleb(-AMOUNT_DECIMAL_PLACES)

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
ERC20_CARRIES_VALUE = "An ERC-20 transfer call cannot also send native currency."
UNSUPPORTED_ENVELOPE = "Only legacy, type 1 and type 2 transactions can be broadcast through this wallet."
SIGNER_MISMATCH = "The signed transaction was signed by {signer}, not by this wallet."
AMOUNT_OUT_OF_RANGE = "The transfer amount is larger than this asset can record."
AMOUNT_TOO_PRECISE = "The transfer amount is finer than this asset can record."


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
    from wallets.services import transaction_confirmation

    chain = normalize_chain(wallet.chain)

    if chain not in SUPPORTED_CHAINS:
        raise UnsupportedChainException(wallet.chain.upper())

    if declared_token_contract:
        transaction_confirmation.resolve_transfer_asset(wallet, declared_token_contract)

    if chain not in EVM_BLOCKCHAINS:
        return None

    return _evm_plan(wallet, signed_transaction)


def _evm_plan(wallet, signed_transaction: str) -> SignedTransferPlan:
    from tokens.models import ShareToken
    from wallets.services import transaction_confirmation
    from wallets.services.transaction_confirmation import NOT_TRANSFERABLE

    decoded = _decode(signed_transaction)
    expected = expected_chain_id(wallet.chain)

    if decoded.sender.lower() != wallet.address.lower():
        raise InvalidTransactionException(SIGNER_MISMATCH.format(signer=decoded.sender))

    if decoded.chain_id is None:
        raise InvalidTransactionException(UNSIGNED_NETWORK)

    if decoded.chain_id != expected:
        raise InvalidTransactionException(WRONG_NETWORK.format(actual=decoded.chain_id, expected=expected))

    if decoded.to is None:
        raise InvalidTransactionException(CONTRACT_CREATION)

    share_token = ShareToken.objects.filter(
        chain__iexact=normalize_chain(wallet.chain), contract_address__iexact=decoded.to
    ).first()
    if share_token is not None:
        raise InvalidTransactionException(NOT_TRANSFERABLE.format(symbol=share_token.symbol))

    if not decoded.data:
        return SignedTransferPlan(
            to_address=decoded.to,
            amount=_recordable(Decimal(from_wei(decoded.value, "ether"))),
            token_contract=None,
        )

    if decoded.value:
        raise InvalidTransactionException(ERC20_CARRIES_VALUE)

    recipient, raw_amount = _erc20_transfer_arguments(decoded.data)
    asset = transaction_confirmation.resolve_transfer_asset(wallet, decoded.to)

    return SignedTransferPlan(
        to_address=recipient,
        amount=_recordable(_scaled(raw_amount, token_deployment_decimals(asset, wallet.chain, decoded.to))),
        token_contract=decoded.to,
    )


def _decode(signed_transaction: str):
    from tokens.services.signed_transactions import (
        UnsupportedEnvelopeError,
        decode_signed_transaction,
    )

    raw = signed_transaction[2:] if signed_transaction.startswith("0x") else signed_transaction

    try:
        return decode_signed_transaction(bytes.fromhex(raw))
    except UnsupportedEnvelopeError:
        raise InvalidTransactionException(UNSUPPORTED_ENVELOPE)
    except ValueError:
        raise InvalidTransactionException(UNDECODABLE)


def _recordable(amount: Decimal) -> Decimal:
    if amount >= AMOUNT_LIMIT:
        raise InvalidTransactionException(AMOUNT_OUT_OF_RANGE)

    with localcontext() as context:
        context.prec = AMOUNT_MAX_DIGITS + 1
        if amount != amount.quantize(AMOUNT_QUANTUM):
            raise InvalidTransactionException(AMOUNT_TOO_PRECISE)

    return amount


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
