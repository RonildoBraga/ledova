import logging
from decimal import Decimal
from typing import Optional

from shared.utils.logging_utils import LoggingContext
from tokens.models import ShareToken, SwapOrder, TransferOrder

logger = logging.getLogger(__name__)


class MarketDataService:

    @staticmethod
    def get_last_trade(token: ShareToken) -> Optional[SwapOrder]:
        return SwapOrder.objects.last_completed_for_token(token)

    @staticmethod
    def calculate_trade_price(swap: SwapOrder) -> Decimal:
        payment_decimals = swap.payment_token.decimals
        payment_full_units = Decimal(swap.payment_amount) / (10**payment_decimals)
        return payment_full_units / Decimal(swap.share_amount)

    @staticmethod
    def get_best_bid_ask(token: ShareToken) -> tuple[Optional[TransferOrder], Optional[TransferOrder]]:
        best_bid = TransferOrder.objects.best_bid(token)
        best_ask = TransferOrder.objects.best_ask(token)
        return best_bid, best_ask

    @staticmethod
    def calculate_midpoint(
        best_bid: Optional[TransferOrder],
        best_ask: Optional[TransferOrder],
    ) -> Optional[Decimal]:
        if best_bid and best_ask:
            return (best_bid.price_per_share + best_ask.price_per_share) / 2
        return None

    @staticmethod
    def get_market_data(token: ShareToken) -> dict:
        last_trade = MarketDataService.get_last_trade(token)

        last_trade_price = None
        last_trade_data = None

        if last_trade:
            last_trade_price = MarketDataService.calculate_trade_price(last_trade)

            last_trade_data = {
                "price": str(last_trade_price),
                "shares": last_trade.share_amount,
                "payment_amount": str(Decimal(last_trade.payment_amount) / (10**last_trade.payment_token.decimals)),
                "payment_token": last_trade.payment_token.symbol,
                "completed_at": (last_trade.completed_at.isoformat() if last_trade.completed_at else None),
            }

        best_bid, best_ask = MarketDataService.get_best_bid_ask(token)
        midpoint_price = MarketDataService.calculate_midpoint(best_bid, best_ask)

        logger.info(
            f"{LoggingContext.TOKEN} Market data for {token.symbol}: "
            f"last_trade={last_trade_price}, bid={best_bid.price_per_share if best_bid else None}, "
            f"ask={best_ask.price_per_share if best_ask else None}"
        )

        return {
            "token": str(token.uuid),
            "symbol": token.symbol,
            "lastTrade": last_trade_data,
            "lastTradePrice": str(last_trade_price) if last_trade_price else None,
            "bestBid": str(best_bid.price_per_share) if best_bid else None,
            "bestAsk": str(best_ask.price_per_share) if best_ask else None,
            "midpointPrice": str(midpoint_price) if midpoint_price else None,
        }
