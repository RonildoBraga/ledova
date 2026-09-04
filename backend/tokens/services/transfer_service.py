import logging
from typing import Optional, Union

from django.db import transaction

from integrations.base_chain import get_base_chain_client
from integrations.base_chain.exceptions import (
    BaseChainContractError,
    BaseChainTransactionError,
)
from tokens.exceptions import (
    InsufficientBalanceException,
    InvalidRecipientAddressException,
    InvalidTokenAddressException,
    NotWhitelistedException,
    OrderMatchException,
    TokenPausedException,
    TransferBroadcastException,
    TransferPreparationException,
)
from tokens.models import (
    ShareToken,
    ShareTokenStatus,
    Stablecoin,
    TransferOrder,
    TransferOrderStatus,
    TransferOrderType,
)
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet
from wallets.models.wallet import Blockchain
from whitelist.services import WhitelistService

logger = logging.getLogger(__name__)


class TransferService:
    def __init__(self):
        self.chain_client = get_base_chain_client()
        self.whitelist_service = WhitelistService()

    def validate_transfer(
        self,
        token: Union[ShareToken, Stablecoin],
        from_address: str,
        to_address: str,
        amount: int,
    ) -> None:
        if isinstance(token, ShareToken) and token.status == ShareTokenStatus.PAUSED:
            raise TokenPausedException()
        if isinstance(token, Stablecoin) and not token.is_active:
            raise TokenPausedException()

        if not token.contract_address:
            raise InvalidTokenAddressException()

        if not self.chain_client.is_valid_address(from_address):
            raise InvalidRecipientAddressException()

        if not self.chain_client.is_valid_address(to_address):
            raise InvalidRecipientAddressException()

        if not self.whitelist_service.is_whitelisted(from_address):
            raise NotWhitelistedException(from_address)

        if not self.whitelist_service.is_whitelisted(to_address):
            raise NotWhitelistedException(to_address)

        from tokens.services import ShareTokenService

        token_service = ShareTokenService()
        balance = token_service.get_token_balance(token.contract_address, from_address)
        if balance < amount:
            raise InsufficientBalanceException(balance, amount)

    def prepare_transfer(
        self,
        token: Union[ShareToken, Stablecoin],
        from_address: str,
        to_address: str,
        amount: int,
    ) -> dict:
        try:
            self.validate_transfer(token, from_address, to_address, amount)

            from_checksum = self.chain_client.to_checksum_address(from_address)
            to_checksum = self.chain_client.to_checksum_address(to_address)

            contract_name = "AUDY" if isinstance(token, Stablecoin) else "ShareToken"
            token_contract = self.chain_client.load_contract(contract_name, token.contract_address)
            transfer_fn = token_contract.functions.transfer(to_checksum, amount)

            nonce = self.chain_client.get_nonce(from_checksum)
            gas_price = self.chain_client.gas_price
            chain_id = self.chain_client.chain_id

            tx_data = {
                "to": token.contract_address,
                "data": transfer_fn._encode_transaction_data(),
                "value": 0,
                "nonce": nonce,
                "chainId": chain_id,
                "gasPrice": gas_price,
            }

            try:
                estimated_gas = self.chain_client.w3.eth.estimate_gas(
                    {
                        "from": from_checksum,
                        "to": token.contract_address,
                        "data": tx_data["data"],
                        "value": 0,
                    }
                )
                tx_data["gas"] = int(estimated_gas * 1.2)
            except Exception:
                tx_data["gas"] = 100000

            logger.info(f"Prepared transfer: {amount} {token.symbol} from {from_checksum} to {to_checksum}")

            return tx_data

        except (NotWhitelistedException, InsufficientBalanceException, TokenPausedException):
            raise
        except Exception as e:
            logger.error(f"Preparation failed: {e}")
            raise TransferPreparationException(f"Transfer preparation failed: {e}") from e

    def broadcast_transfer(self, signed_tx: str) -> tuple[str, dict]:
        try:
            if signed_tx.startswith("0x"):
                signed_tx_bytes = bytes.fromhex(signed_tx[2:])
            else:
                signed_tx_bytes = bytes.fromhex(signed_tx)

            tx_hash = self.chain_client.send_raw_transaction(signed_tx_bytes)
            receipt = self.chain_client.wait_for_receipt(tx_hash)

            logger.info(f"Broadcast successful: {tx_hash}")

            return tx_hash, dict(receipt)

        except (BaseChainTransactionError, BaseChainContractError) as e:
            logger.error(f"Broadcast failed: {e}")
            raise TransferBroadcastException(f"Transfer broadcast failed: {e}") from e
        except ValueError as e:
            logger.error(f"Invalid transaction hex: {e}")
            raise TransferBroadcastException("Transfer broadcast failed: Invalid transaction format") from e

    @transaction.atomic
    def match_orders(
        self, buy_order: TransferOrder, sell_order: TransferOrder, match_quantity: Optional[int] = None
    ) -> dict:
        if buy_order.order_type != TransferOrderType.BUY:
            raise OrderMatchException("First order must be a buy order")

        if sell_order.order_type != TransferOrderType.SELL:
            raise OrderMatchException("Second order must be a sell order")

        if buy_order.token_id != sell_order.token_id:
            raise OrderMatchException("Orders must be for the same token")

        if buy_order.status not in [TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED]:
            raise OrderMatchException(f"Buy order status {buy_order.status} cannot be matched")

        if sell_order.status not in [TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED]:
            raise OrderMatchException(f"Sell order status {sell_order.status} cannot be matched")

        if buy_order.price_per_share < sell_order.price_per_share:
            raise OrderMatchException(
                f"Price mismatch: buy price {buy_order.price_per_share} < sell price {sell_order.price_per_share}"
            )

        buy_remaining = buy_order.quantity - (buy_order.filled_quantity or 0)
        sell_remaining = sell_order.quantity - (sell_order.filled_quantity or 0)

        if match_quantity is None:
            match_quantity = min(buy_remaining, sell_remaining)

        if match_quantity <= 0:
            raise OrderMatchException("Match quantity must be positive")

        if match_quantity > buy_remaining:
            raise OrderMatchException(f"Match quantity {match_quantity} exceeds buy remaining {buy_remaining}")

        if match_quantity > sell_remaining:
            raise OrderMatchException(f"Match quantity {match_quantity} exceeds sell remaining {sell_remaining}")

        buy_min = buy_order.min_quantity or 0
        sell_min = sell_order.min_quantity or 0

        if buy_min > 0 and match_quantity < buy_min:
            raise OrderMatchException(f"Match quantity {match_quantity} below buy min_quantity {buy_min}")

        if sell_min > 0 and match_quantity < sell_min:
            raise OrderMatchException(f"Match quantity {match_quantity} below sell min_quantity {sell_min}")

        execution_price = sell_order.price_per_share

        buy_order.partial_match_with(sell_order, match_quantity)

        from tokens.services import AtomicSwapService

        atomic_swap_service = AtomicSwapService()
        swap_order = atomic_swap_service.create_swap_order(
            sell_order=sell_order,
            buy_order=buy_order,
            share_amount=match_quantity,
            price_per_share=execution_price,
        )

        logger.info(
            f"Orders matched: buy={buy_order.uuid}, "
            f"sell={sell_order.uuid}, qty={match_quantity}, price={execution_price}, swap={swap_order.uuid}"
        )

        return {
            "buy_order": buy_order,
            "sell_order": sell_order,
            "swap_order": swap_order,
            "matched_quantity": match_quantity,
            "execution_price": str(execution_price),
        }

    def find_matching_order(self, order: TransferOrder) -> Optional[tuple[TransferOrder, int]]:
        if order.order_type == TransferOrderType.BUY:
            qs = (
                TransferOrder.objects.ownership_bound()
                .open_or_partial()
                .sell_orders()
                .filter(
                    token=order.token,
                    price_per_share__lte=order.price_per_share,  # Sell price <= buy price
                )
            )
            qs = qs.order_by("price_per_share", "created_at")
        else:
            qs = (
                TransferOrder.objects.ownership_bound()
                .open_or_partial()
                .buy_orders()
                .filter(
                    token=order.token,
                    price_per_share__gte=order.price_per_share,  # Buy price >= sell price
                )
            )
            qs = qs.order_by("-price_per_share", "created_at")

        qs = qs.exclude(wallet_address__iexact=order.wallet_address).select_for_update(of=("self",))

        order_remaining = order.quantity - (order.filled_quantity or 0)

        for candidate in qs:
            candidate_remaining = candidate.quantity - (candidate.filled_quantity or 0)

            match_qty = min(order_remaining, candidate_remaining)

            if match_qty <= 0:
                continue

            order_min = order.min_quantity or 0
            candidate_min = candidate.min_quantity or 0

            if order_min > 0 and match_qty < order_min:
                continue

            if candidate_min > 0 and match_qty < candidate_min:
                continue

            return (candidate, match_qty)

        return None

    @transaction.atomic
    def create_order_and_match(
        self,
        token: ShareToken,
        order_type: TransferOrderType,
        actor,
        wallet,
        owner_account,
        wallet_address: str,
        quantity: int,
        price_per_share,
        min_quantity: int = 0,
    ) -> tuple[TransferOrder, Optional[dict]]:
        try:
            wallet = Wallet.objects.select_for_update(of=("self",)).select_related("user_account").get(pk=wallet.pk)
        except Wallet.DoesNotExist:
            raise InvalidRecipientAddressException()

        if wallet.user_account_id != owner_account.pk:
            raise InvalidRecipientAddressException()

        membership_model = wallet.user_account.user_profiles.through
        actor_is_current_member = (
            actor is not None
            and actor.is_authenticated
            and membership_model.objects.select_for_update(of=("self",))
            .filter(
                useraccount_id=wallet.user_account_id,
                userprofile__user=actor,
            )
            .exists()
        )
        if not actor_is_current_member:
            raise InvalidRecipientAddressException()

        if wallet.verification_status != WALLET_VERIFICATION_STATUS_VERIFIED:
            raise InvalidRecipientAddressException()
        if wallet.chain not in (Blockchain.ETHEREUM.value, Blockchain.BASE.value):
            raise InvalidRecipientAddressException()

        if not self.chain_client.is_valid_address(wallet.address):
            raise InvalidRecipientAddressException()

        canonical_wallet_address = self.chain_client.to_checksum_address(wallet.address)
        if canonical_wallet_address != self.chain_client.to_checksum_address(wallet_address):
            raise InvalidRecipientAddressException()

        if not self.whitelist_service.is_whitelisted(canonical_wallet_address):
            raise NotWhitelistedException(canonical_wallet_address)

        if order_type == TransferOrderType.SELL:
            from tokens.services import ShareTokenService

            token_service = ShareTokenService()
            balance = token_service.get_token_balance(token.contract_address, canonical_wallet_address)
            if balance < quantity:
                raise InsufficientBalanceException(balance, quantity)

        order = TransferOrder.objects.create(
            token=token,
            order_type=order_type,
            wallet=wallet,
            owner_account=wallet.user_account,
            wallet_address=canonical_wallet_address,
            quantity=quantity,
            min_quantity=min_quantity,
            price_per_share=price_per_share,
            filled_quantity=0,
        )

        match_info = self.find_matching_order(order)

        if match_info:
            matching_order, match_quantity = match_info
            if order_type == TransferOrderType.BUY:
                match_result = self.match_orders(order, matching_order, match_quantity)
            else:
                match_result = self.match_orders(matching_order, order, match_quantity)

            from tokens.events import publish_trading_event

            publish_trading_event("order_created", str(token.uuid))
            publish_trading_event("order_matched", str(token.uuid))
            return order, match_result

        from tokens.events import publish_trading_event

        publish_trading_event("order_created", str(token.uuid))
        return order, None
