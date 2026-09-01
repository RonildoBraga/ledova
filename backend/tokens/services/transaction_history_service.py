import logging
from typing import Optional

from shared.utils.logging_utils import LoggingContext
from tokens.models import MintRequest, ShareIssuance, SwapOrder

logger = logging.getLogger(__name__)


class TransactionHistoryService:
    @staticmethod
    def get_transaction_history(
        wallet_ids,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        transaction_type: Optional[str] = None,
    ) -> dict:
        """Return history that can be bound to the caller's authorized wallet rows.

        MintRequest and ShareIssuance currently store only recipient-address
        snapshots, not tenant or wallet foreign keys. Customer API callers receive
        no rows from those sources until the schema can enforce ownership.
        """
        if not wallet_ids:
            logger.warning(f"{LoggingContext.TOKEN} No authorized wallets provided")
            return {
                "swap_orders": SwapOrder.objects.none(),
                "mint_requests": MintRequest.objects.none(),
                "token_issuances": ShareIssuance.objects.none(),
            }

        result = {"swap_orders": None, "mint_requests": None, "token_issuances": None}

        if not transaction_type or transaction_type == "trade":
            qs = SwapOrder.objects.completed().for_wallet_ids(wallet_ids)
            if start_date:
                qs = qs.filter(completed_at__gte=start_date)
            if end_date:
                qs = qs.filter(completed_at__lte=end_date)
            result["swap_orders"] = qs.with_tokens()

        if not transaction_type or transaction_type in ("stablecoin_mint", "yield_token_mint"):
            result["mint_requests"] = MintRequest.objects.none()

        if not transaction_type or transaction_type == "token_issuance":
            result["token_issuances"] = ShareIssuance.objects.none()

        return result

    @staticmethod
    def merge_and_sort_transactions(
        swap_order_data: list,
        mint_request_data: list,
        token_issuance_data: list = None,
        sort_key: str = "blockTimestamp",
        descending: bool = True,
    ) -> list:
        all_transactions = []

        if swap_order_data:
            all_transactions.extend(swap_order_data)

        if mint_request_data:
            all_transactions.extend(mint_request_data)

        if token_issuance_data:
            all_transactions.extend(token_issuance_data)

        all_transactions.sort(
            key=lambda x: x.get(sort_key) or "",
            reverse=descending,
        )

        return all_transactions
