from decimal import Decimal

from tokens.models import ShareToken, SwapOrder, TransferOrder


class MarketDataService:

    @staticmethod
    def get_market_data(token: ShareToken) -> dict:
        last_trade = SwapOrder.objects.last_completed_for_token(token)
        best_bid = TransferOrder.objects.best_bid(token)
        best_ask = TransferOrder.objects.best_ask(token)

        last_trade_price = None
        last_trade_data = None
        if last_trade:
            payment_full_units = Decimal(last_trade.payment_amount) / (10**last_trade.payment_token.decimals)
            last_trade_price = payment_full_units / Decimal(last_trade.share_amount)
            last_trade_data = {
                "price": str(last_trade_price),
                "shares": last_trade.share_amount,
                "payment_amount": str(payment_full_units),
                "payment_token": last_trade.payment_token.symbol,
                "completed_at": (last_trade.completed_at.isoformat() if last_trade.completed_at else None),
            }

        midpoint_price = (best_bid.price_per_share + best_ask.price_per_share) / 2 if best_bid and best_ask else None

        return {
            "token": str(token.uuid),
            "symbol": token.symbol,
            "lastTrade": last_trade_data,
            "lastTradePrice": str(last_trade_price) if last_trade_price else None,
            "bestBid": str(best_bid.price_per_share) if best_bid else None,
            "bestAsk": str(best_ask.price_per_share) if best_ask else None,
            "midpointPrice": str(midpoint_price) if midpoint_price else None,
        }
