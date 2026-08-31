SYMBOL_TO_COINGECKO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "POL": "polygon-ecosystem-token",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "USDC": "usd-coin",
    "USDT": "tether",
    "USDD": "usdd",
}

COINGECKO_ID_TO_SYMBOL = {v: k for k, v in SYMBOL_TO_COINGECKO_ID.items()}
