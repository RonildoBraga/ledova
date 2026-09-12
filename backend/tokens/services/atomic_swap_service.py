import logging
import secrets
from collections.abc import Mapping
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.utils import timezone
from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_typed_data
from web3 import Web3

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain import get_base_chain_client
from operators.settlement import require_deployment
from shared.db import atomic, use_operator
from shared.utils.blockchain import decode_exception_to_message
from tokens.events import publish_trading_event
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
from tokens.services.settlement_context import (
    SettlementApprovalUncertain,
    SettlementContextChanged,
    assert_current_settlement,
    capture_settlement_context,
    recorded_settlement_context,
    settlement_execution_arguments,
)
from tokens.services.signed_transactions import decode_signed_transaction
from tokens.services.trading_locks import (
    hash_identity,
    lock_current_claim,
    lock_orders,
    swap_terms,
)
from whitelist.services import WhitelistService

logger = logging.getLogger(__name__)

MAX_UINT256 = 2**256 - 1


def payment_address(swap_order) -> str:
    if swap_order.settlement_protocol_version:
        return recorded_settlement_context(swap_order)["typed_data"]["message"]["paymentToken"]
    return require_deployment(swap_order.payment_asset).contract_address


class AtomicSwapService:

    DOMAIN_NAME = "LedovaAtomicSwap"
    DOMAIN_VERSION = "1"

    def __init__(self):
        self._chain_client = None
        self._whitelist_service = None

    @property
    def chain_client(self):
        if self._chain_client is None:
            self._chain_client = get_base_chain_client()
        return self._chain_client

    @chain_client.setter
    def chain_client(self, value):
        self._chain_client = value

    @property
    def whitelist_service(self):
        if self._whitelist_service is None:
            self._whitelist_service = WhitelistService()
        return self._whitelist_service

    @whitelist_service.setter
    def whitelist_service(self, value):
        self._whitelist_service = value

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
        if swap_order.settlement_protocol_version:
            return recorded_settlement_context(swap_order)["typed_data"]
        deadline = int(swap_order.expires_at.timestamp())

        return {
            "types": self._get_eip712_types(),
            "primaryType": "SwapOrder",
            "domain": self._get_eip712_domain(),
            "message": {
                "seller": swap_order.seller_address,
                "buyer": swap_order.buyer_address,
                "shareToken": swap_order.share_token.contract_address,
                "paymentToken": payment_address(swap_order),
                "shareAmount": str(swap_order.share_amount),
                "paymentAmount": str(swap_order.payment_amount),
                "nonce": str(swap_order.nonce),
                "deadline": str(deadline),
            },
        }

    def _generate_nonce(self) -> int:
        return secrets.randbits(63)

    def _compute_order_hash(self, swap_order: SwapOrder) -> str:
        typed_data = self.get_typed_data(swap_order)
        structured_message = encode_typed_data(full_message=typed_data)
        return structured_message.body.hex()

    def settlement_contract(self, swap_order):
        if swap_order.settlement_protocol_version:
            return recorded_settlement_context(swap_order)["typed_data"]["domain"]["verifyingContract"]
        return self.contract_address

    def assert_provider_settlement(self, swap_order, chain_client=None):
        if swap_order.settlement_protocol_version:
            context = assert_current_settlement(swap_order)
            try:
                actual_chain = (chain_client if chain_client is not None else self.chain_client).assert_expected_chain()
            except Exception as exc:
                raise SettlementContextChanged() from exc
            if actual_chain != int(context["typed_data"]["domain"]["chainId"]):
                raise SettlementContextChanged()
            assert_current_settlement(swap_order)

    def check_allowance(self, token_address: str, owner_address: str, spender=None) -> int:
        token_contract = self.chain_client.load_contract("ShareToken", token_address)
        allowance = self.chain_client.call_contract_function(
            token_contract.functions.allowance(
                self.chain_client.to_checksum_address(owner_address),
                self.chain_client.to_checksum_address(spender or self.contract_address),
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
        self.assert_provider_settlement(swap_order)
        context = recorded_settlement_context(swap_order) if swap_order.settlement_protocol_version else None
        seller_balance = self.check_balance(
            context["share_token"]["address"] if context else swap_order.share_token.contract_address,
            swap_order.seller_address,
        )
        if seller_balance < swap_order.share_amount:
            raise InsufficientBalanceException(
                balance=seller_balance,
                required=swap_order.share_amount,
                token_symbol=context["share_token"]["symbol"] if context else swap_order.share_token.symbol,
            )

        buyer_balance = self.check_balance(
            payment_address(swap_order),
            swap_order.buyer_address,
        )
        if buyer_balance < swap_order.payment_amount:
            raise InsufficientBalanceException(
                balance=buyer_balance,
                required=swap_order.payment_amount,
                token_symbol=context["payment_asset"]["symbol"] if context else swap_order.payment_asset.symbol,
                decimals=context["payment_asset"]["pricing_decimals"] if context else swap_order.payment_asset.decimals,
            )
        self.assert_provider_settlement(swap_order)

    def check_swap_allowances(self, swap_order: SwapOrder) -> dict:
        self.assert_provider_settlement(swap_order)
        context = recorded_settlement_context(swap_order) if swap_order.settlement_protocol_version else None
        share_address = context["share_token"]["address"] if context else swap_order.share_token.contract_address
        spender = self.settlement_contract(swap_order)
        seller_allowance = self.check_allowance(
            share_address,
            swap_order.seller_address,
            spender,
        )
        seller_has_allowance = seller_allowance >= swap_order.share_amount

        buyer_allowance = self.check_allowance(
            payment_address(swap_order),
            swap_order.buyer_address,
            spender,
        )
        buyer_has_allowance = buyer_allowance >= swap_order.payment_amount

        self.assert_provider_settlement(swap_order)
        return {
            "seller": {
                "address": swap_order.seller_address,
                "token": share_address,
                "token_symbol": context["share_token"]["symbol"] if context else swap_order.share_token.symbol,
                "required_amount": swap_order.share_amount,
                "current_allowance": seller_allowance,
                "has_sufficient_allowance": seller_has_allowance,
            },
            "buyer": {
                "address": swap_order.buyer_address,
                "token": payment_address(swap_order),
                "token_symbol": context["payment_asset"]["symbol"] if context else swap_order.payment_asset.symbol,
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
        self.assert_provider_settlement(swap_order)
        context = recorded_settlement_context(swap_order) if swap_order.settlement_protocol_version else None
        if user_role == "seller":
            token_address = context["share_token"]["address"] if context else swap_order.share_token.contract_address
            owner_address = swap_order.seller_address
            amount = MAX_UINT256 if unlimited else swap_order.share_amount
            token_symbol = context["share_token"]["symbol"] if context else swap_order.share_token.symbol
        elif user_role == "buyer":
            token_address = payment_address(swap_order)
            owner_address = swap_order.buyer_address
            amount = MAX_UINT256 if unlimited else swap_order.payment_amount
            token_symbol = context["payment_asset"]["symbol"] if context else swap_order.payment_asset.symbol
        else:
            raise ValueError(f"Invalid user_role: {user_role}")

        token_contract = self.chain_client.load_contract("ShareToken", token_address)
        approve_fn = token_contract.functions.approve(
            self.chain_client.to_checksum_address(self.settlement_contract(swap_order)),
            amount,
        )
        tx = self.chain_client.build_transaction(
            approve_fn,
            from_address=owner_address,
        )
        self.assert_provider_settlement(swap_order)
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
            "spender": self.settlement_contract(swap_order),
            "amount": str(amount),
            "unlimited": unlimited,
        }

    def broadcast_settlement_approval(self, swap_order, user_role, signed_transaction, admission):
        from tokens.services.token_transfer_service import TokenTransferService
        from tokens.services.trading_order_access import require_pending_settlement

        context = require_pending_settlement(swap_order)
        try:
            raw_transaction = bytes.fromhex(signed_transaction.removeprefix("0x"))
            decoded = decode_signed_transaction(raw_transaction)
        except ValueError as exc:
            raise SettlementContextChanged() from exc
        token = (
            context["share_token"]["address"]
            if user_role == "seller"
            else context["payment_asset"]["deployment_address"]
        )
        spender = context["typed_data"]["domain"]["verifyingContract"]
        expected_data = (
            bytes.fromhex("095ea7b3") + bytes.fromhex(spender[2:]).rjust(32, b"\x00") + MAX_UINT256.to_bytes(32, "big")
        )
        if (
            decoded.sender != context[user_role]["address"]
            or decoded.chain_id != int(context["typed_data"]["domain"]["chainId"])
            or decoded.to != token
            or decoded.value != 0
            or decoded.data != expected_data
        ):
            raise SettlementContextChanged()
        transfer_service = TokenTransferService()
        self.assert_provider_settlement(swap_order, transfer_service.chain_client)
        current = admission(swap_order)
        require_pending_settlement(current)
        expected_hash = Web3.to_hex(Web3.keccak(raw_transaction))
        try:
            returned_hash, receipt = transfer_service.broadcast_transfer(signed_transaction)
            if (
                hash_identity(returned_hash) != hash_identity(expected_hash)
                or hash_identity(receipt.get("transactionHash")) != hash_identity(expected_hash)
                or type(receipt.get("status")) is not int
                or receipt["status"] != 1
            ):
                raise SettlementApprovalUncertain(expected_hash)
        except Exception as exc:
            raise SettlementApprovalUncertain(expected_hash) from exc
        return expected_hash, receipt

    @atomic()
    def create_swap_order(
        self,
        sell_order: TransferOrder,
        buy_order: TransferOrder,
        expires_hours: Optional[float] = None,
        share_amount: Optional[int] = None,
        price_per_share=None,
    ) -> SwapOrder:
        locked = {
            order.pk: order for order in lock_orders(TransferOrder.objects.filter(pk__in=[sell_order.pk, buy_order.pk]))
        }
        sell_order = locked[sell_order.pk]
        buy_order = locked[buy_order.pk]
        if sell_order.order_type != TransferOrderType.SELL:
            raise ValueError("sell_order must be a SELL order")
        if buy_order.order_type != TransferOrderType.BUY:
            raise ValueError("buy_order must be a BUY order")

        token = sell_order.token
        payment_asset = buy_order.payment_asset or sell_order.payment_asset

        if not payment_asset:
            raise ValueError("Payment asset must be specified on at least one order")

        if share_amount is None:
            share_amount = sell_order.quantity

        if price_per_share is None:
            price_per_share = sell_order.price_per_share

        payment_amount = int(share_amount * price_per_share * (10**payment_asset.decimals))
        nonce = self._generate_nonce()

        if expires_hours is None:
            expires_hours = getattr(settings, "SWAP_ORDER_EXPIRY_HOURS", 0.25)
        expires_at = timezone.now() + timedelta(hours=expires_hours)

        swap_order = SwapOrder(
            sell_order=sell_order,
            buy_order=buy_order,
            share_token=token,
            payment_asset=payment_asset,
            seller_address=Web3.to_checksum_address(sell_order.wallet_address),
            buyer_address=Web3.to_checksum_address(buy_order.wallet_address),
            share_amount=share_amount,
            payment_amount=payment_amount,
            nonce=nonce,
            order_hash="",
            expires_at=expires_at,
            expiry_release_eligible=True,
            status=SwapOrderStatus.CREATED,
        )
        capture_settlement_context(swap_order, price_per_share)
        swap_order.save()

        sell_order.status = TransferOrderStatus.PENDING_SIGNATURE
        sell_order.save(update_fields=["status", "updated_at"])
        buy_order.status = TransferOrderStatus.PENDING_SIGNATURE
        buy_order.save(update_fields=["status", "updated_at"])

        logger.info(f"Created swap order {swap_order.uuid}: {share_amount} shares for {payment_amount} payment")

        return swap_order

    def verify_signature(self, swap_order: SwapOrder, signature: str, expected_signer: str) -> bool:
        try:
            typed_data = self.get_typed_data(swap_order)
            structured_message = encode_typed_data(full_message=typed_data)
            recovered = Account.recover_message(structured_message, signature=signature)
            expected_checksum = Web3.to_checksum_address(expected_signer)

            return recovered.lower() == expected_checksum.lower()
        except Exception as e:
            logger.warning(f"Signature verification failed: {e}", exc_info=True)
            return False

    def submit_signature(
        self,
        swap_order: SwapOrder,
        signature: str,
        signer_address: str,
        admission=None,
    ) -> SwapOrder:
        snapshot = SwapOrder.objects.get(pk=swap_order.pk)
        if admission:
            admission(snapshot)
        signer_checksum = Web3.to_checksum_address(signer_address)
        if signer_checksum == Web3.to_checksum_address(snapshot.seller_address):
            is_seller = True
            expected_signer = snapshot.seller_address
        elif signer_checksum == Web3.to_checksum_address(snapshot.buyer_address):
            is_seller = False
            expected_signer = snapshot.buyer_address
        else:
            raise SwapSignatureException("Signer is neither the buyer nor seller")
        if not self.verify_signature(snapshot, signature, expected_signer):
            raise SwapSignatureException("Invalid signature")
        return self._store_signature(snapshot, signature, is_seller, admission=admission)

    @atomic()
    def _store_signature(self, snapshot, signature, is_seller, admission=None):
        swap = SwapOrder.objects.select_for_update(of=("self",)).get(pk=snapshot.pk)
        if swap_terms(swap) != swap_terms(snapshot):
            raise SwapSignatureException("The swap changed while its signature was being checked")
        if admission:
            admission(swap)
        stored = swap.seller_signature if is_seller else swap.buyer_signature
        if stored:
            if stored != signature:
                raise SwapSignatureException("This party has already signed the swap")
            return swap
        if swap.settlement_protocol_version:
            assert_current_settlement(swap)
        allowed = (
            (SwapOrderStatus.CREATED, SwapOrderStatus.BUYER_SIGNED)
            if is_seller
            else (SwapOrderStatus.CREATED, SwapOrderStatus.SELLER_SIGNED)
        )
        if swap.status not in allowed or swap.transaction_id is not None or swap.tx_hash:
            raise SwapNotReadyException()
        if swap.deadline_passed:
            raise SwapExpiredException()
        if is_seller:
            swap.add_seller_signature(signature)
        else:
            swap.add_buyer_signature(signature)
        publish_trading_event("swap_signed", str(swap.share_token_id))
        return swap

    def execute_swap(self, swap_order: SwapOrder, admission=None) -> str:
        if admission:
            admission(swap_order)
        self.assert_provider_settlement(swap_order)
        swap, tx_record = self._claim_execution(swap_order.pk, admission=admission)
        try:
            self.validate_swap_balances(swap)
            signed_tx = self._prepare_attempt(swap)
        except SettlementContextChanged:
            raise
        except Exception as exc:
            told_to_the_parties = decode_exception_to_message(exc, "Swap execution failed")
            self._record_never_sent(swap, tx_record, str(exc), told_to_the_parties)
            if isinstance(exc, InsufficientBalanceException):
                raise
            raise SwapExecutionException(f"Swap execution failed: {told_to_the_parties}") from exc
        self.assert_provider_settlement(swap)
        if admission:
            admission(swap)
        if swap.settlement_protocol_version:
            self._admit_claim(swap, tx_record)
        try:
            tx_hash = self.chain_client.send_raw_transaction(signed_tx)
        except Exception as exc:
            self._record_unknown_fate(swap, tx_record, str(exc))
            raise SwapExecutionException(
                f"Swap execution outcome is unknown: {decode_exception_to_message(exc, 'no response from the chain')}"
            ) from exc
        return self._record_broadcast(swap, tx_record, tx_hash)

    @atomic()
    def _admit_claim(self, swap, transaction):
        current = lock_current_claim(swap, transaction)
        if current is None:
            raise SwapNotReadyException()
        assert_current_settlement(current[0])
        if current[0].deadline_passed:
            raise SwapExpiredException()

    @atomic(durable=True)
    def _claim_execution(self, swap_id, admission=None):
        swap = SwapOrder.objects.select_for_update(of=("self",)).get(pk=swap_id)
        if not swap.is_ready or swap.transaction_id is not None or swap.tx_hash:
            raise SwapNotReadyException()
        if swap.deadline_passed:
            raise SwapExpiredException()
        if admission:
            admission(swap)
        if swap.settlement_protocol_version:
            assert_current_settlement(swap)
        relayer_account = Account.from_key(self.relayer_private_key)
        arguments = (
            settlement_execution_arguments(swap)
            if swap.settlement_protocol_version
            else {
                "seller": swap.seller_address,
                "buyer": swap.buyer_address,
                "shareToken": swap.share_token.contract_address,
                "paymentToken": payment_address(swap),
                "shareAmount": str(swap.share_amount),
                "paymentAmount": str(swap.payment_amount),
                "nonce": str(swap.nonce),
            }
        )
        tx_record = self._new_transaction_record(swap, relayer_account.address, arguments)
        swap.mark_executing(transaction=tx_record)
        return swap, tx_record

    def _prepare_attempt(self, swap_order: SwapOrder):
        self.assert_provider_settlement(swap_order)
        relayer_account = Account.from_key(self.relayer_private_key)
        execute_fn = self._execute_swap_call(swap_order)
        tx = self.chain_client.build_transaction(execute_fn, from_address=relayer_account.address)
        return self.chain_client.sign_transaction(tx, self.relayer_private_key)

    def _execute_swap_call(self, swap_order: SwapOrder):
        contract = self.chain_client.load_contract("AtomicSwap", self.settlement_contract(swap_order))
        message = self.get_typed_data(swap_order)["message"]

        return contract.functions.executeSwap(
            Web3.to_checksum_address(message["seller"]),
            Web3.to_checksum_address(message["buyer"]),
            Web3.to_checksum_address(message["shareToken"]),
            Web3.to_checksum_address(message["paymentToken"]),
            int(message["shareAmount"]),
            int(message["paymentAmount"]),
            int(message["nonce"]),
            int(message["deadline"]),
            _signature_bytes(swap_order.seller_signature),
            _signature_bytes(swap_order.buyer_signature),
        )

    def _new_transaction_record(self, swap_order: SwapOrder, relayer_address: str, arguments: dict):
        return BlockchainTransaction.objects.create(
            tx_type=TransactionType.ATOMIC_SWAP,
            status=TransactionStatus.PENDING,
            from_address=relayer_address,
            to_address=self.settlement_contract(swap_order),
            function_name="executeSwap",
            function_args=arguments,
            related_model="tokens.SwapOrder",
            related_uuid=swap_order.uuid,
        )

    @atomic(durable=True)
    def _record_never_sent(self, swap_order, tx_record, raw_error, told_to_the_parties):
        current = lock_current_claim(swap_order, tx_record, with_orders=True)
        if current is None:
            return
        swap, transaction = current
        if transaction.tx_hash or transaction.status not in (TransactionStatus.PENDING, TransactionStatus.FAILED):
            return
        transaction.mark_failed(raw_error)
        swap.mark_failed(told_to_the_parties)
        logger.error("Swap %s was never sent", swap.uuid)
        publish_trading_event("swap_failed", str(swap.share_token_id))

    @atomic()
    def _record_unknown_fate(self, swap_order, tx_record, raw_error):
        current = lock_current_claim(swap_order, tx_record)
        if current is None:
            return
        _swap, transaction = current
        if transaction.status not in (TransactionStatus.CONFIRMED, TransactionStatus.REVERTED):
            transaction.mark_outcome_unknown(raw_error)

    def _record_broadcast(self, swap_order, tx_record, tx_hash):
        current = self._record_sent(swap_order, tx_record, tx_hash)
        if current is None:
            return tx_hash
        swap, transaction = current
        try:
            receipt = self.chain_client.receipt_even_if_reverted(tx_hash)
        except Exception:
            logger.warning("Swap %s has a recorded broadcast and no receipt yet", swap.uuid)
            return tx_hash
        self._record_receipt(swap, transaction, tx_hash, receipt)
        return tx_hash

    @atomic()
    def _record_sent(self, swap_order, tx_record, tx_hash):
        current = lock_current_claim(swap_order, tx_record)
        if current is None or not hash_identity(tx_hash):
            return None
        swap, transaction = current
        if transaction.tx_hash and hash_identity(transaction.tx_hash) != hash_identity(tx_hash):
            return None
        if transaction.status in (TransactionStatus.CONFIRMED, TransactionStatus.REVERTED):
            return current if transaction.tx_hash else None
        if transaction.status != TransactionStatus.SUBMITTED or not transaction.tx_hash:
            transaction.mark_submitted(tx_hash)
        if not swap.tx_hash:
            swap.mark_executing(tx_hash, transaction=transaction)
        return swap, transaction

    @atomic()
    def _record_receipt(self, swap_order, tx_record, tx_hash, receipt):
        if not isinstance(receipt, Mapping) or receipt.get("status") not in (0, 1):
            return None
        if not hash_identity(tx_hash):
            return None
        receipt_hash = receipt.get("transactionHash")
        if receipt_hash is not None and hash_identity(receipt_hash) != hash_identity(tx_hash):
            return None
        current = lock_current_claim(swap_order, tx_record, with_orders=True)
        if current is None:
            return None
        swap, transaction = current
        if hash_identity(transaction.tx_hash) != hash_identity(tx_hash):
            return None
        if receipt["status"] == 1:
            if transaction.status == TransactionStatus.REVERTED:
                return None
            if transaction.status != TransactionStatus.CONFIRMED:
                block_hash = receipt.get("blockHash", "")
                transaction.mark_confirmed(
                    block_number=receipt.get("blockNumber"),
                    block_hash=block_hash.hex() if isinstance(block_hash, bytes) else block_hash,
                    gas_used=receipt.get("gasUsed"),
                )
            swap.mark_completed()
            publish_trading_event("swap_completed", str(swap.share_token_id))
            return "executed"
        if transaction.status == TransactionStatus.CONFIRMED:
            return None
        reason = f"The chain reverted the swap: {tx_hash}"
        if transaction.status != TransactionStatus.REVERTED:
            transaction.mark_reverted(reason)
        swap.mark_failed(reason)
        publish_trading_event("swap_failed", str(swap.share_token_id))
        return "reverted"

    def executed_order_hash(self, swap_order: SwapOrder) -> str:
        signable = encode_typed_data(full_message=self.get_typed_data(swap_order))
        return _hash_eip191_message(signable).hex()

    def chain_says_this_swap_executed(self, swap_order: SwapOrder, receipt=None) -> bool:
        if not swap_order.tx_hash:
            return False
        if receipt is None:
            receipt = self.chain_client.receipt_even_if_reverted(swap_order.tx_hash)
        if not isinstance(receipt, Mapping) or receipt.get("status") != 1:
            return False
        if swap_order.settlement_protocol_version:
            recorded = recorded_settlement_context(swap_order)
            if self.chain_client.w3.eth.chain_id != int(recorded["typed_data"]["domain"]["chainId"]):
                return False
        contract = self.chain_client.load_contract("AtomicSwap", self.settlement_contract(swap_order))
        expected = self.executed_order_hash(swap_order)
        for event in contract.events.SwapExecuted().process_receipt(receipt):
            if hash_identity(event["args"]["orderHash"]) == hash_identity(expected):
                return True
        return False

    def is_nonce_used(self, account: str, nonce: int) -> bool:
        contract = self.chain_client.load_contract("AtomicSwap", self.contract_address)
        return contract.functions.isNonceUsed(self.chain_client.to_checksum_address(account), nonce).call()

    def resolve_executing_swap(self, swap_order: SwapOrder) -> Optional[str]:
        if swap_order.status != SwapOrderStatus.EXECUTING or not swap_order.transaction_id or not swap_order.tx_hash:
            return None
        transaction = BlockchainTransaction.objects.get(pk=swap_order.transaction_id)
        if hash_identity(transaction.tx_hash) != hash_identity(swap_order.tx_hash):
            return None
        receipt = self.chain_client.receipt_even_if_reverted(swap_order.tx_hash)
        if isinstance(receipt, Mapping) and receipt.get("status") == 1:
            if not self.chain_says_this_swap_executed(swap_order, receipt):
                return None
        return self._record_receipt(swap_order, transaction, swap_order.tx_hash, receipt)

    def find_swap_order_by_transfer_order(self, transfer_order: TransferOrder) -> Optional[SwapOrder]:
        return SwapOrder.objects.for_transfer_order(transfer_order)

    def is_share_token_approved(self, token_address: str) -> bool:
        try:
            contract = self.chain_client.load_contract("AtomicSwap", self.contract_address)
            checksum = self.chain_client.to_checksum_address(token_address)
            return contract.functions.approvedShareTokens(checksum).call()
        except Exception as e:
            logger.error(f"Error checking token approval: {e}")
            return False

    def approve_share_token(self, token_address: str) -> Optional[str]:
        try:
            checksum = self.chain_client.to_checksum_address(token_address)

            if self.is_share_token_approved(checksum):
                logger.info(f"ShareToken {checksum} already approved in AtomicSwap")
                return None

            logger.info(f"Approving ShareToken {checksum} in AtomicSwap contract")

            contract = self.chain_client.load_contract("AtomicSwap", self.contract_address)
            approve_fn = contract.functions.setShareTokenApproval(checksum, True)

            tx_hash, receipt = self.chain_client.send_transaction(
                approve_fn,
                self.relayer_private_key,
                wait_for_receipt=True,
            )

            if receipt and receipt.get("status") == 1:
                logger.info(f"ShareToken {checksum} approved in AtomicSwap - tx: {tx_hash}")
                return tx_hash
            else:
                logger.error("ShareToken approval transaction reverted")
                return None

        except Exception as e:
            logger.error(f"Failed to approve ShareToken in AtomicSwap: {e}")
            return None


def sign_and_execute_swap(service, swap_order, signature: str, signer_address: str, admission=None):
    options = {"admission": admission} if admission else {}
    with use_operator():
        signed = service.submit_signature(
            swap_order=swap_order, signature=signature, signer_address=signer_address, **options
        )

        if signed.is_ready:
            logger.info(f"Both signatures present, executing swap {signed.uuid}")
            service.execute_swap(signed, **options)
            signed.refresh_from_db()

    return signed


def _signature_bytes(signature: str) -> bytes:
    return bytes.fromhex(signature[2:] if signature.startswith("0x") else signature)
