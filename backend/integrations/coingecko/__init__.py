"""
CoinGecko integration for cryptocurrency market data.

Provides access to:
- Real-time cryptocurrency prices
- Market cap, volume, and 24h price changes
- Asset metadata

Usage:
    from integrations.coingecko import CoinGeckoClient, SYMBOL_TO_COINGECKO_ID

    client = CoinGeckoClient()
    prices = client.fetch_prices_by_symbols({"BTC": "bitcoin", "ETH": "ethereum"})
"""

from integrations.coingecko.client import CoinGeckoClient
from integrations.coingecko.constants import (
    COINGECKO_ID_TO_SYMBOL,
    SYMBOL_TO_COINGECKO_ID,
)

__all__ = [
    "CoinGeckoClient",
    "SYMBOL_TO_COINGECKO_ID",
    "COINGECKO_ID_TO_SYMBOL",
]
