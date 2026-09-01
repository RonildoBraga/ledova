import logging
from typing import Optional

from shared.utils.logging_utils import LoggingContext
from tokens.models import MintRequest, ShareIssuance, SwapOrder

logger = logging.getLogger(__name__)


class TransactionHistoryService:
    @staticmethod
    def get_transaction_history(
        wallet_ids,
        wallet_addresses: list[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        transaction_type: Optional[str] = None,
        include_address_only_history: bool = False,
    ) -> dict:
        """Return history that can be bound to the caller's authorized wallet rows.

        MintRequest and ShareIssuance currently store only recipient-address
        snapshots, not tenant or wallet foreign keys. Nonstaff callers therefore
        receive no rows from those sources until the schema can enforce ownership;
        otherwise a duplicate address registered by another tenant would disclose
        history. Staff access remains explicitly address-bounded.
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
            if include_address_only_history:
                qs = MintRequest.objects.executed().filter_by_recipient_addresses(wallet_addresses)
                if start_date:
                    qs = qs.filter(executed_at__gte=start_date)
                if end_date:
                    qs = qs.filter(executed_at__lte=end_date)
                result["mint_requests"] = qs.with_related()
            else:
                result["mint_requests"] = MintRequest.objects.none()

        if not transaction_type or transaction_type == "token_issuance":
            if include_address_only_history:
                result["token_issuances"] = (
                    ShareIssuance.objects.completed()
                    .filter_by_recipients(wallet_addresses)
                    .filter_by_date_range(start_date, end_date)
                    .with_token()
                )
            else:
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
