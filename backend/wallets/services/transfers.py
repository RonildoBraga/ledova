import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from eth_utils import from_wei, to_wei
from web3 import Web3

from integrations.blockchain import get_blockchain_client
from shared.constants import (
    BLOCKCHAIN_BITCOIN,
    EVM_BLOCKCHAINS,
    SUPPORTED_CHAINS,
    normalize_chain,
)
from wallets.exceptions import (
    BlockchainAPIError,
    InsufficientBalanceException,
    InvalidTransactionException,
    UnsupportedChainException,
)

logger = logging.getLogger(__name__)


class TransferService:

    @staticmethod
    def prepare_transfer(
        wallet,
        to_address: str,
        amount_eth: Optional[str] = None,
        amount_btc: Optional[str] = None,
        amount_token: Optional[str] = None,
        token_contract: Optional[str] = None,
    ) -> Dict[str, Any]:
        chain = normalize_chain(wallet.chain)

        if chain not in SUPPORTED_CHAINS:
            raise UnsupportedChainException(wallet.chain.upper())

        if chain in EVM_BLOCKCHAINS and token_contract:
            return TransferService._prepare_erc20_transfer(
                wallet=wallet,
                chain=chain,
                to_address=to_address,
                amount_token=amount_token,
                token_contract=token_contract,
            )

        if chain in EVM_BLOCKCHAINS:
            if not to_address or not amount_eth:
                raise InvalidTransactionException(
                    "Both 'toAddress' and 'amountEth' are required for Ethereum transfers."
                )
            amount = TransferService._parse_amount(amount_eth)
            current_balance = TransferService._get_native_balance(wallet)

            return prepare_ethereum_transaction(
                chain=chain,
                from_address=wallet.address,
                to_address=to_address,
                amount_eth=amount,
                current_balance=current_balance,
            )

        if chain == BLOCKCHAIN_BITCOIN:
            if not to_address or not amount_btc:
                raise InvalidTransactionException(
                    "Both 'toAddress' and 'amountBtc' are required for Bitcoin transfers."
                )
            amount = TransferService._parse_amount(amount_btc)
            current_balance = TransferService._get_native_balance(wallet)

            return prepare_bitcoin_transaction(
                from_address=wallet.address,
                to_address=to_address,
                amount_btc=amount,
                current_balance=current_balance,
            )

        raise UnsupportedChainException(chain.upper())

    @staticmethod
    def _prepare_erc20_transfer(
        wallet,
        chain: str,
        to_address: str,
        amount_token: Optional[str],
        token_contract: str,
    ) -> Dict[str, Any]:
        from assets.models import Asset
        from wallets.models import Holding

        if not to_address or not amount_token:
            raise InvalidTransactionException("Both 'toAddress' and 'amountToken' are required for token transfers.")

        amount = TransferService._parse_amount(amount_token)

        token_asset = Asset.get_by_chain_and_contract(wallet.chain, token_contract)
        if not token_asset:
            raise InvalidTransactionException(f"Token contract {token_contract} not found on {wallet.chain}.")

        token_holding = Holding.objects.filter(wallet=wallet, asset=token_asset).first()
        token_balance = token_holding.quantity if token_holding else Decimal("0")

        eth_balance = TransferService._get_native_balance(wallet)

        return prepare_erc20_transaction(
            chain=chain,
            from_address=wallet.address,
            to_address=to_address,
            amount=amount,
            token_balance=token_balance,
            eth_balance=eth_balance,
            contract_address=token_contract,
            token_symbol=token_asset.symbol,
            token_decimals=token_asset.decimals or 18,
        )

    @staticmethod
    def broadcast_transfer(
        wallet,
        signed_transaction: str,
        to_address: Optional[str] = None,
        amount: Optional[str] = None,
        transaction_fee: Optional[str] = None,
        token_contract: Optional[str] = None,
    ) -> Dict[str, Any]:
        chain = normalize_chain(wallet.chain)

        if chain not in SUPPORTED_CHAINS:
            raise UnsupportedChainException(wallet.chain.upper())

        if not signed_transaction:
            raise InvalidTransactionException("'signedTransaction' is required.")

        if chain in EVM_BLOCKCHAINS:
            tx_hash = broadcast_ethereum_transaction(chain, signed_transaction)
        elif chain == BLOCKCHAIN_BITCOIN:
            tx_hash = broadcast_bitcoin_transaction(signed_transaction)
        else:
            raise UnsupportedChainException(chain.upper())

        pending_result = None
        if to_address and amount:
            from wallets.services.transaction_confirmation import (
                TransactionConfirmationService,
            )

            amount_decimal = Decimal(amount)
            fee_decimal = Decimal(transaction_fee) if transaction_fee else None

            pending_result = TransactionConfirmationService.create_pending_transaction(
                wallet=wallet,
                tx_hash=tx_hash,
                to_address=to_address,
                amount=amount_decimal,
                transaction_fee=fee_decimal,
                token_contract=token_contract,
            )

        TransferService._schedule_confirmation_checks(tx_hash, str(wallet.uuid))

        return {
            "success": True,
            "txHash": tx_hash,
            "status": "pending",
            "message": f"Transaction broadcast successfully! Transaction hash: {tx_hash}",
            "pendingTransaction": pending_result,
        }

    @staticmethod
    def _schedule_confirmation_checks(tx_hash: str, wallet_uuid: str) -> None:
        from wallets.tasks import confirm_pending_transaction

        confirm_pending_transaction.configure(schedule_in={"seconds": 30}).defer(
            tx_hash=tx_hash, wallet_uuid=wallet_uuid
        )

        confirm_pending_transaction.configure(schedule_in={"seconds": 120}).defer(
            tx_hash=tx_hash, wallet_uuid=wallet_uuid
        )

    @staticmethod
    def _parse_amount(amount_str: str) -> Decimal:
        try:
            return Decimal(amount_str)
        except (ValueError, TypeError, InvalidOperation):
            raise InvalidTransactionException("Invalid amount format. Must be a valid decimal number.")

    @staticmethod
    def _get_native_balance(wallet) -> Decimal:
        from assets.models import Asset
        from wallets.models import Holding

        native_asset = Asset.objects.native_for_chain(wallet.chain)
        quantity = Holding.objects.filter(wallet=wallet, asset=native_asset).values_list("quantity", flat=True).first()
        return quantity or Decimal("0")


def prepare_ethereum_transaction(
    chain: str, from_address: str, to_address: str, amount_eth: Decimal, current_balance: Decimal
) -> Dict[str, Any]:
    logger.info(f"Preparing transaction: from={from_address[:8]}..., to={to_address[:8]}..., amount={amount_eth} ETH")

    try:
        if not from_address or not to_address:
            raise InvalidTransactionException("Invalid sender or recipient address")

        if amount_eth <= 0:
            raise InvalidTransactionException("Transfer amount must be greater than zero")

        from_address_checksum = Web3.to_checksum_address(from_address)
        to_address_checksum = Web3.to_checksum_address(to_address)

        client = get_blockchain_client(chain)
        gas_price_wei = client.get_gas_price()

        gas_limit = 21000
        gas_cost_wei = gas_price_wei * gas_limit
        gas_cost_eth = Decimal(from_wei(gas_cost_wei, "ether"))

        total_cost_eth = amount_eth + gas_cost_eth

        if current_balance < total_cost_eth:
            logger.warning(f"Insufficient balance: available={current_balance} ETH, required={total_cost_eth} ETH")
            raise InsufficientBalanceException(
                f"Insufficient balance. Available: {current_balance} ETH, "
                f"Required: {total_cost_eth} ETH (including {gas_cost_eth} ETH gas fee)"
            )

        nonce = client.w3.eth.get_transaction_count(from_address_checksum)
        amount_wei = int(to_wei(float(amount_eth), "ether"))

        transaction = {
            "nonce": nonce,
            "to": to_address_checksum,
            "value": amount_wei,
            "gas": gas_limit,
            "gasPrice": gas_price_wei,
            "chainId": client.w3.eth.chain_id,
        }

        logger.info(
            "Transaction prepared: "
            f"nonce={nonce}, gas_price={gas_price_wei} Wei, gas_limit={gas_limit}, "
            f"amount={amount_eth} ETH, gas_cost={gas_cost_eth} ETH, total={total_cost_eth} ETH"
        )

        return {
            "transaction": transaction,
            "amount_eth": str(amount_eth),
            "gas_price_wei": str(gas_price_wei),
            "gas_price_gwei": str(Decimal(gas_price_wei) / Decimal(10**9)),
            "gas_limit": gas_limit,
            "gas_cost_eth": str(gas_cost_eth),
            "total_cost_eth": str(total_cost_eth),
            "from_address": from_address,
            "to_address": to_address,
        }

    except (InsufficientBalanceException, InvalidTransactionException):
        raise
    except Exception as e:
        logger.error(f"Error preparing transaction: {str(e)}", exc_info=True)
        raise BlockchainAPIError(f"Failed to prepare transaction: {str(e)}")


def prepare_bitcoin_transaction(
    from_address: str, to_address: str, amount_btc: Decimal, current_balance: Decimal
) -> Dict[str, Any]:
    logger.info(
        f"Preparing Bitcoin transaction: from={from_address[:8]}..., to={to_address[:8]}..., amount={amount_btc} BTC"
    )

    try:
        if not from_address or not to_address:
            raise InvalidTransactionException("Invalid sender or recipient address")

        if amount_btc <= 0:
            raise InvalidTransactionException("Transfer amount must be greater than zero")

        client = get_blockchain_client("BTC")
        fee_per_byte = client.get_gas_price()

        estimated_tx_size = 250
        fee_satoshis = int(fee_per_byte * estimated_tx_size)
        fee_btc = Decimal(fee_satoshis) / Decimal(10**8)

        total_cost_btc = amount_btc + fee_btc

        if current_balance < total_cost_btc:
            logger.warning(f"Insufficient balance: available={current_balance} BTC, required={total_cost_btc} BTC")
            raise InsufficientBalanceException(
                f"Insufficient balance. Available: {current_balance} BTC, "
                f"Required: {total_cost_btc} BTC (including {fee_btc} BTC fee)"
            )

        amount_satoshis = int(amount_btc * Decimal(10**8))

        logger.info(
            "Bitcoin transaction prepared: "
            f"fee_per_byte={fee_per_byte} sat/byte, estimated_size={estimated_tx_size} bytes, "
            f"amount={amount_btc} BTC, fee={fee_btc} BTC, total={total_cost_btc} BTC"
        )

        return {
            "from_address": from_address,
            "to_address": to_address,
            "amount_btc": str(amount_btc),
            "amount_satoshis": amount_satoshis,
            "fee_per_byte": str(fee_per_byte),
            "estimated_tx_size": estimated_tx_size,
            "fee_satoshis": fee_satoshis,
            "fee_btc": str(fee_btc),
            "total_cost_btc": str(total_cost_btc),
            "network": "BTC",
        }

    except (InsufficientBalanceException, InvalidTransactionException):
        raise
    except Exception as e:
        logger.error(f"Error preparing Bitcoin transaction: {str(e)}", exc_info=True)
        raise BlockchainAPIError(f"Failed to prepare Bitcoin transaction: {str(e)}")


def broadcast_ethereum_transaction(chain: str, signed_tx_hex: str) -> str:
    try:
        logger.info(f"Broadcasting signed {chain} transaction")

        client = get_blockchain_client(chain)
        tx_hash = client.broadcast_transaction(signed_tx_hex)

        logger.info(f"Ethereum transaction broadcast successful: {tx_hash}")
        return tx_hash

    except Exception as e:
        logger.error(f"Failed to broadcast Ethereum transaction: {str(e)}")
        raise BlockchainAPIError(f"Failed to broadcast transaction: {str(e)}")


def broadcast_bitcoin_transaction(signed_tx_hex: str) -> str:
    try:
        logger.info("Broadcasting signed Bitcoin transaction")

        client = get_blockchain_client("BTC")
        tx_hash = client.broadcast_transaction(signed_tx_hex)

        logger.info(f"Bitcoin transaction broadcast successful: {tx_hash}")
        return tx_hash

    except Exception as e:
        logger.error(f"Failed to broadcast Bitcoin transaction: {str(e)}")
        raise BlockchainAPIError(f"Failed to broadcast transaction: {str(e)}")


def prepare_erc20_transaction(
    chain: str,
    from_address: str,
    to_address: str,
    amount: Decimal,
    token_balance: Decimal,
    eth_balance: Decimal,
    contract_address: str,
    token_symbol: str,
    token_decimals: int,
) -> Dict[str, Any]:
    logger.info(
        "Preparing ERC-20 transaction: "
        f"from={from_address[:8]}..., to={to_address[:8]}..., amount={amount} {token_symbol}"
    )

    try:
        if not from_address or not to_address:
            raise InvalidTransactionException("Invalid sender or recipient address")

        if amount <= 0:
            raise InvalidTransactionException("Transfer amount must be greater than zero")

        if token_balance < amount:
            logger.warning(
                "Insufficient token balance: "
                f"available={token_balance} {token_symbol}, required={amount} {token_symbol}"
            )
            raise InsufficientBalanceException(
                f"Insufficient {token_symbol} balance. Available: {token_balance}, Required: {amount}"
            )

        contract_checksum = Web3.to_checksum_address(contract_address)

        client = get_blockchain_client(chain)

        gas_limit = client.estimate_erc20_transfer_gas(
            from_address=from_address,
            contract_address=contract_address,
            recipient=to_address,
            amount=amount,
            decimals=token_decimals,
        )

        gas_price_wei = client.get_gas_price()
        gas_cost_wei = gas_price_wei * gas_limit
        gas_cost_eth = Decimal(from_wei(gas_cost_wei, "ether"))

        if eth_balance < gas_cost_eth:
            logger.warning(f"Insufficient ETH for gas: available={eth_balance} ETH, required={gas_cost_eth} ETH")
            raise InsufficientBalanceException(
                f"Insufficient ETH for gas fees. Available: {eth_balance} ETH, Required: {gas_cost_eth} ETH"
            )

        encoded_data = client.build_erc20_transfer_data(
            contract_address=contract_address,
            recipient=to_address,
            amount=amount,
            decimals=token_decimals,
        )

        nonce = client.get_nonce(from_address)

        transaction = {
            "nonce": nonce,
            "to": contract_checksum,
            "value": 0,
            "data": encoded_data,
            "gas": gas_limit,
            "gasPrice": gas_price_wei,
            "chainId": client.w3.eth.chain_id,
        }

        logger.info(
            "ERC-20 transaction prepared: "
            f"nonce={nonce}, gas_price={gas_price_wei} Wei, gas_limit={gas_limit}, "
            f"amount={amount} {token_symbol}, gas_cost={gas_cost_eth} ETH"
        )

        return {
            "transaction": transaction,
            "amount_token": str(amount),
            "token_symbol": token_symbol,
            "token_decimals": token_decimals,
            "token_contract": contract_address,
            "gas_price_wei": str(gas_price_wei),
            "gas_price_gwei": str(Decimal(gas_price_wei) / Decimal(10**9)),
            "gas_limit": gas_limit,
            "gas_cost_eth": str(gas_cost_eth),
            "from_address": from_address,
            "to_address": to_address,
        }

    except (InsufficientBalanceException, InvalidTransactionException):
        raise
    except Exception as e:
        logger.error(f"Error preparing ERC-20 transaction: {str(e)}", exc_info=True)
        raise BlockchainAPIError(f"Failed to prepare ERC-20 transaction: {str(e)}")
