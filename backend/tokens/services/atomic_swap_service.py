import logging
import secrets
import time
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from eth_account import Account
from eth_account.messages import encode_typed_data
from rest_framework.exceptions import PermissionDenied

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain import get_base_chain_client
from integrations.base_chain.exceptions import (
    BaseChainContractError,
    BaseChainTransactionError,
)
from shared.utils.blockchain import decode_exception_to_message
from shared.utils.logging_utils import LoggingContext
from tokens.exceptions import (
    AtomicSwapNotConfiguredException,
    InsufficientBalanceException,
    SwapExecutionException,
    SwapExpiredException,
    SwapNotReadyException,
    SwapSignatureException,
)
from tokens.models import (
    SwapOrder,
    SwapOrderStatus,
    TransferOrder,
    TransferOrderStatus,
    TransferOrderType,
)
from whitelist.services import WhitelistService

logger = logging.getLogger(__name__)

MAX_UINT256 = 2**256 - 1


class AtomicSwapService:

    DOMAIN_NAME = "LedovaAtomicSwap"
    DOMAIN_VERSION = "1"

    def __init__(self):
        self.chain_client = get_base_chain_client()
        self.whitelist_service = WhitelistService()

    @property
    def contract_address(self) -> str:
        address = getattr(settings, "ATOMIC_SWAP_ADDRESS", None)
        if not address:
            raise AtomicSwapNotConfiguredException()
        return address

    @property
    def relayer_private_key(self) -> str:
        key = getattr(settings, "BLOCKCHAIN_OPERATOR_KEY", None)
        if not key:
            raise AtomicSwapNotConfiguredException("Relayer private key not configured")
        return key

    def _get_eip712_domain(self) -> dict:
        return {
            "name": self.DOMAIN_NAME,
            "version": self.DOMAIN_VERSION,
            "chainId": self.chain_client.chain_id,
            "verifyingContract": self.contract_address,
        }

    def _get_eip712_types(self) -> dict:
        return {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "SwapOrder": [
                {"name": "seller", "type": "address"},
                {"name": "buyer", "type": "address"},
                {"name": "shareToken", "type": "address"},
                {"name": "paymentToken", "type": "address"},
                {"name": "shareAmount", "type": "uint256"},
                {"name": "paymentAmount", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ],
        }

    def get_typed_data(self, swap_order: SwapOrder) -> dict:
        deadline = int(swap_order.expires_at.timestamp())

        return {
            "types": self._get_eip712_types(),
            "primaryType": "SwapOrder",
            "domain": self._get_eip712_domain(),
            "message": {
                "seller": swap_order.seller_address,
                "buyer": swap_order.buyer_address,
                "shareToken": swap_order.share_token.contract_address,
                "paymentToken": swap_order.payment_token.contract_address,
                "shareAmount": swap_order.share_amount,
                "paymentAmount": swap_order.payment_amount,
                "nonce": swap_order.nonce,
                "deadline": deadline,
            },
        }

    def _generate_nonce(self) -> int:
        return int(time.time() * 1000000) + secrets.randbelow(1000000)

    def _compute_order_hash(self, swap_order: SwapOrder) -> str:
        typed_data = self.get_typed_data(swap_order)
        structured_message = encode_typed_data(full_message=typed_data)
        return structured_message.body.hex()

    def check_allowance(self, token_address: str, owner_address: str) -> int:
        token_contract = self.chain_client.load_contract("ShareToken", token_address)
        allowance = self.chain_client.call_contract_function(
            token_contract.functions.allowance(
                self.chain_client.to_checksum_address(owner_address),
                self.chain_client.to_checksum_address(self.contract_address),
            )
        )
        return allowance

    def check_balance(self, token_address: str, owner_address: str) -> int:
        token_contract = self.chain_client.load_contract("ShareToken", token_address)
        balance = self.chain_client.call_contract_function(
            token_contract.functions.balanceOf(
                self.chain_client.to_checksum_address(owner_address),
            )
        )
        return balance

    def validate_swap_balances(self, swap_order: SwapOrder) -> None:
        seller_balance = self.check_balance(
            swap_order.share_token.contract_address,
            swap_order.seller_address,
        )
        if seller_balance < swap_order.share_amount:
            raise InsufficientBalanceException(
                balance=seller_balance,
                required=swap_order.share_amount,
                token_symbol=swap_order.share_token.symbol,
            )

        buyer_balance = self.check_balance(
            swap_order.payment_token.contract_address,
            swap_order.buyer_address,
        )
        if buyer_balance < swap_order.payment_amount:
            raise InsufficientBalanceException(
                balance=buyer_balance,
                required=swap_order.payment_amount,
                token_symbol=swap_order.payment_token.symbol,
                decimals=swap_order.payment_token.decimals,
            )

    def check_swap_allowances(self, swap_order: SwapOrder) -> dict:
        seller_allowance = self.check_allowance(
            swap_order.share_token.contract_address,
            swap_order.seller_address,
        )
        seller_has_allowance = seller_allowance >= swap_order.share_amount

        buyer_allowance = self.check_allowance(
            swap_order.payment_token.contract_address,
            swap_order.buyer_address,
        )
        buyer_has_allowance = buyer_allowance >= swap_order.payment_amount

        return {
            "seller": {
                "address": swap_order.seller_address,
                "token": swap_order.share_token.contract_address,
                "token_symbol": swap_order.share_token.symbol,
                "required_amount": swap_order.share_amount,
                "current_allowance": seller_allowance,
                "has_sufficient_allowance": seller_has_allowance,
            },
            "buyer": {
                "address": swap_order.buyer_address,
                "token": swap_order.payment_token.contract_address,
                "token_symbol": swap_order.payment_token.symbol,
                "required_amount": swap_order.payment_amount,
                "current_allowance": buyer_allowance,
                "has_sufficient_allowance": buyer_has_allowance,
            },
        }

    def get_approval_transaction_data(
        self,
        swap_order: SwapOrder,
        user_role: str,
        unlimited: bool = True,
    ) -> dict:
        if user_role == "seller":
            token_address = swap_order.share_token.contract_address
            owner_address = swap_order.seller_address
            amount = MAX_UINT256 if unlimited else swap_order.share_amount
            token_symbol = swap_order.share_token.symbol
        elif user_role == "buyer":
            token_address = swap_order.payment_token.contract_address
            owner_address = swap_order.buyer_address
            amount = MAX_UINT256 if unlimited else swap_order.payment_amount
            token_symbol = swap_order.payment_token.symbol
        else:
            raise ValueError(f"Invalid user_role: {user_role}")

        token_contract = self.chain_client.load_contract("ShareToken", token_address)
        approve_fn = token_contract.functions.approve(
            self.chain_client.to_checksum_address(self.contract_address),
            amount,
        )
        tx = self.chain_client.build_transaction(
            approve_fn,
            from_address=owner_address,
        )

        return {
            "transaction": {
                "to": token_address,
                "from": owner_address,
                "data": tx.get("data", ""),
                "value": "0x0",
                "gas": hex(tx.get("gas", 100000)),
                "gasPrice": hex(tx.get("gasPrice", 0)),
                "nonce": hex(tx.get("nonce", 0)),
                "chainId": hex(self.chain_client.chain_id),
            },
            "description": f"Approve AtomicSwap contract to transfer {token_symbol}",
            "token_address": token_address,
            "token_symbol": token_symbol,
            "spender": self.contract_address,
            "amount": str(amount),
            "unlimited": unlimited,
        }

    @transaction.atomic
    def create_swap_order(
        self,
        sell_order: TransferOrder,
        buy_order: TransferOrder,
        expires_hours: Optional[int] = None,
        share_amount: Optional[int] = None,
        price_per_share=None,
    ) -> SwapOrder:
        if sell_order.order_type != TransferOrderType.SELL:
            raise ValueError("sell_order must be a SELL order")
        if buy_order.order_type != TransferOrderType.BUY:
            raise ValueError("buy_order must be a BUY order")

        token = sell_order.token
        payment_token = buy_order.payment_token or sell_order.payment_token

        if not payment_token:
            raise ValueError("Payment token must be specified on at least one order")

        if share_amount is None:
            share_amount = sell_order.quantity

        if price_per_share is None:
            price_per_share = sell_order.price_per_share

        payment_amount = int(share_amount * price_per_share * (10**payment_token.decimals))
        nonce = self._generate_nonce()

        if expires_hours is None:
            expires_hours = getattr(settings, "SWAP_ORDER_EXPIRY_HOURS", 24)
        expires_at = timezone.now() + timedelta(hours=expires_hours)

        swap_order = SwapOrder(
            sell_order=sell_order,
            buy_order=buy_order,
            share_token=token,
            payment_token=payment_token,
            seller_address=self.chain_client.to_checksum_address(sell_order.wallet_address),
            buyer_address=self.chain_client.to_checksum_address(buy_order.wallet_address),
            share_amount=share_amount,
            payment_amount=payment_amount,
            nonce=nonce,
            order_hash="",
            expires_at=expires_at,
            status=SwapOrderStatus.CREATED,
        )
        swap_order.order_hash = self._compute_order_hash(swap_order)
        swap_order.save()

        sell_order.status = TransferOrderStatus.PENDING_SIGNATURE
        sell_order.save(update_fields=["status", "updated_at"])
        buy_order.status = TransferOrderStatus.PENDING_SIGNATURE
        buy_order.save(update_fields=["status", "updated_at"])

        logger.info(
            f"{LoggingContext.TOKEN_TRANSFER} Created swap order {swap_order.uuid}: "
            f"{share_amount} shares for {payment_amount} payment"
        )

        return swap_order

    def verify_signature(self, swap_order: SwapOrder, signature: str, expected_signer: str) -> bool:
        try:
            typed_data = self.get_typed_data(swap_order)
            structured_message = encode_typed_data(full_message=typed_data)
            recovered = Account.recover_message(structured_message, signature=signature)
            expected_checksum = self.chain_client.to_checksum_address(expected_signer)

            return recovered.lower() == expected_checksum.lower()
        except Exception as e:
            logger.warning(f"Signature verification failed: {e}", exc_info=True)
            return False

    @transaction.atomic
    def submit_signature(
        self,
        swap_order: SwapOrder,
        signature: str,
        signer_address: str,
    ) -> SwapOrder:
        logger.info(
            f"{LoggingContext.TOKEN_TRANSFER} submit_signature called - "
            f"swap={swap_order.uuid}, signer={signer_address}"
        )

        if swap_order.is_expired:
            logger.warning(f"{LoggingContext.TOKEN_TRANSFER} Swap {swap_order.uuid} is expired")
            raise SwapExpiredException()

        signer_checksum = self.chain_client.to_checksum_address(signer_address)
        seller_checksum = self.chain_client.to_checksum_address(swap_order.seller_address)
        buyer_checksum = self.chain_client.to_checksum_address(swap_order.buyer_address)

        logger.info(
            f"{LoggingContext.TOKEN_TRANSFER} Address comparison - "
            f"signer={signer_checksum}, seller={seller_checksum}, buyer={buyer_checksum}"
        )

        if signer_checksum == seller_checksum:
            expected_signer = swap_order.seller_address
            is_seller = True
            logger.info(f"{LoggingContext.TOKEN_TRANSFER} Signer identified as SELLER")
        elif signer_checksum == buyer_checksum:
            expected_signer = swap_order.buyer_address
            is_seller = False
            logger.info(f"{LoggingContext.TOKEN_TRANSFER} Signer identified as BUYER")
        else:
            logger.error(
                f"{LoggingContext.TOKEN_TRANSFER} Signer {signer_checksum} is neither "
                f"seller {seller_checksum} nor buyer {buyer_checksum}"
            )
            raise SwapSignatureException("Signer is neither the buyer nor seller")

        logger.info(f"{LoggingContext.TOKEN_TRANSFER} Verifying signature for {expected_signer}")
        if not self.verify_signature(swap_order, signature, expected_signer):
            logger.error(
                f"{LoggingContext.TOKEN_TRANSFER} Signature verification failed for "
                f"swap={swap_order.uuid}, signer={expected_signer}"
            )
            raise SwapSignatureException("Invalid signature")

        logger.info(f"{LoggingContext.TOKEN_TRANSFER} Signature verified successfully")

        if is_seller:
            swap_order.add_seller_signature(signature)
            logger.info(f"{LoggingContext.TOKEN_TRANSFER} Seller signed swap {swap_order.uuid}")
        else:
            swap_order.add_buyer_signature(signature)
            logger.info(f"{LoggingContext.TOKEN_TRANSFER} Buyer signed swap {swap_order.uuid}")

        logger.info(f"{LoggingContext.TOKEN_TRANSFER} Swap {swap_order.uuid} ready status: {swap_order.is_ready}")

        from tokens.events import publish_trading_event

        publish_trading_event("swap_signed", str(swap_order.share_token.uuid))

        if swap_order.is_ready:
            logger.info(f"{LoggingContext.TOKEN_TRANSFER} Both signatures present, executing swap")
            self.execute_swap(swap_order)

        return swap_order

    def execute_swap(self, swap_order: SwapOrder) -> str:
        if not swap_order.is_ready:
            raise SwapNotReadyException()

        if swap_order.is_expired:
            raise SwapExpiredException()

        self.validate_swap_balances(swap_order)

        relayer_account = Account.from_key(self.relayer_private_key)
        relayer_address = relayer_account.address

        tx_record = BlockchainTransaction.objects.create(
            tx_type=TransactionType.ATOMIC_SWAP,
            status=TransactionStatus.PENDING,
            from_address=relayer_address,
            to_address=self.contract_address,
            function_name="executeSwap",
            function_args={
                "seller": swap_order.seller_address,
                "buyer": swap_order.buyer_address,
                "shareToken": swap_order.share_token.contract_address,
                "paymentToken": swap_order.payment_token.contract_address,
                "shareAmount": str(swap_order.share_amount),
                "paymentAmount": str(swap_order.payment_amount),
                "nonce": str(swap_order.nonce),
            },
            related_model="tokens.SwapOrder",
            related_uuid=swap_order.uuid,
        )

        try:
            contract = self.chain_client.load_contract("AtomicSwap", self.contract_address)
            deadline = int(swap_order.expires_at.timestamp())

            execute_fn = contract.functions.executeSwap(
                self.chain_client.to_checksum_address(swap_order.seller_address),
                self.chain_client.to_checksum_address(swap_order.buyer_address),
                self.chain_client.to_checksum_address(swap_order.share_token.contract_address),
                self.chain_client.to_checksum_address(swap_order.payment_token.contract_address),
                swap_order.share_amount,
                swap_order.payment_amount,
                swap_order.nonce,
                deadline,
                bytes.fromhex(
                    swap_order.seller_signature[2:]
                    if swap_order.seller_signature.startswith("0x")
                    else swap_order.seller_signature
                ),
                bytes.fromhex(
                    swap_order.buyer_signature[2:]
                    if swap_order.buyer_signature.startswith("0x")
                    else swap_order.buyer_signature
                ),
            )

            tx_hash, receipt = self.chain_client.send_transaction(
                execute_fn,
                self.relayer_private_key,
            )

            tx_record.mark_submitted(tx_hash)
            swap_order.mark_executing(tx_hash, transaction=tx_record)

            if receipt and receipt.get("status") == 1:
                tx_record.mark_confirmed(
                    block_number=receipt.get("blockNumber"),
                    block_hash=(
                        receipt.get("blockHash", "").hex()
                        if isinstance(receipt.get("blockHash"), bytes)
                        else receipt.get("blockHash", "")
                    ),
                    gas_used=receipt.get("gasUsed"),
                )
                swap_order.mark_completed()
                logger.info(f"{LoggingContext.TOKEN_TRANSFER} Swap {swap_order.uuid} completed: {tx_hash}")

                from tokens.events import publish_trading_event

                publish_trading_event("swap_completed", str(swap_order.share_token.uuid))
            else:
                tx_record.mark_reverted("Transaction reverted")
                swap_order.mark_failed("Transaction reverted")
                logger.error(f"{LoggingContext.TOKEN_TRANSFER} Swap {swap_order.uuid} failed: {tx_hash}")

                from tokens.events import publish_trading_event

                publish_trading_event("swap_failed", str(swap_order.share_token.uuid))

            return tx_hash

        except (BaseChainContractError, BaseChainTransactionError) as e:
            raw_error = str(e)
            user_friendly_msg = decode_exception_to_message(e, "Swap execution failed")
            tx_record.mark_failed(raw_error)
            swap_order.mark_failed(raw_error)
            logger.error(f"{LoggingContext.TOKEN_TRANSFER} Swap execution failed: {raw_error}")

            from tokens.events import publish_trading_event

            publish_trading_event("swap_failed", str(swap_order.share_token.uuid))
            raise SwapExecutionException(f"Swap execution failed: {user_friendly_msg}") from e
        except InsufficientBalanceException:
            raise
        except Exception as e:
            raw_error = str(e)
            user_friendly_msg = decode_exception_to_message(e, "Swap execution failed")
            tx_record.mark_failed(raw_error)
            swap_order.mark_failed(raw_error)
            logger.error(f"{LoggingContext.TOKEN_TRANSFER} Swap execution error: {raw_error}")

            from tokens.events import publish_trading_event

            publish_trading_event("swap_failed", str(swap_order.share_token.uuid))
            raise SwapExecutionException(f"Swap execution failed: {user_friendly_msg}") from e

    def get_pending_swaps_for_wallet_ids(self, wallet_ids):
        """Return a lazy owner-bound queryset so the API can paginate in SQL."""
        return SwapOrder.objects.pending_for_wallet_ids(wallet_ids)

    def determine_user_role(self, swap_order: SwapOrder, wallet_address: str) -> dict:
        wallet_checksum = self.chain_client.to_checksum_address(wallet_address)
        seller_checksum = self.chain_client.to_checksum_address(swap_order.seller_address)
        buyer_checksum = self.chain_client.to_checksum_address(swap_order.buyer_address)

        if wallet_checksum == seller_checksum:
            return {
                "role": "seller",
                "has_signed": swap_order.seller_has_signed,
                "is_valid": True,
            }
        elif wallet_checksum == buyer_checksum:
            return {
                "role": "buyer",
                "has_signed": swap_order.buyer_has_signed,
                "is_valid": True,
            }
        else:
            raise PermissionDenied("Wallet address is not a party to this swap.")

    def find_swap_order_by_transfer_order(self, transfer_order: TransferOrder) -> Optional[SwapOrder]:
        return SwapOrder.objects.for_transfer_order(transfer_order)

    def is_share_token_approved(self, token_address: str) -> bool:
        try:
            contract = self.chain_client.load_contract("AtomicSwap", self.contract_address)
            checksum = self.chain_client.to_checksum_address(token_address)
            return contract.functions.approvedShareTokens(checksum).call()
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN} Error checking token approval: {e}")
            return False

    def is_payment_token_approved(self, token_address: str) -> bool:
        try:
            contract = self.chain_client.load_contract("AtomicSwap", self.contract_address)
            checksum = self.chain_client.to_checksum_address(token_address)
            return contract.functions.approvedPaymentTokens(checksum).call()
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN} Error checking payment token approval: {e}")
            return False

    def approve_share_token(self, token_address: str) -> Optional[str]:
        try:
            checksum = self.chain_client.to_checksum_address(token_address)

            if self.is_share_token_approved(checksum):
                logger.info(f"{LoggingContext.TOKEN} ShareToken {checksum} already approved in AtomicSwap")
                return None

            logger.info(f"{LoggingContext.TOKEN} Approving ShareToken {checksum} in AtomicSwap contract")

            contract = self.chain_client.load_contract("AtomicSwap", self.contract_address)
            approve_fn = contract.functions.setShareTokenApproval(checksum, True)

            tx_hash, receipt = self.chain_client.send_transaction(
                approve_fn,
                self.relayer_private_key,
                wait_for_receipt=True,
            )

            if receipt and receipt.get("status") == 1:
                logger.info(f"{LoggingContext.TOKEN} ShareToken {checksum} approved in AtomicSwap - tx: {tx_hash}")
                return tx_hash
            else:
                logger.error(f"{LoggingContext.TOKEN} ShareToken approval transaction reverted")
                return None

        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN} Failed to approve ShareToken in AtomicSwap: {e}")
            return None
