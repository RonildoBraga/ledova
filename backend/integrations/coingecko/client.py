"""
CoinGecko API client for fetching cryptocurrency market data.

Provides access to:
- Real-time prices
- Historical prices
- Market cap, volume, 24h changes
- Asset metadata

Free tier (no API key required):
- Rate limit: 10-50 calls/minute
- Endpoint: https://api.coingecko.com/api/v3
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


class CoinGeckoClient:
    """
    Client for CoinGecko API.

    Fetches cryptocurrency market data including prices, market cap,
    volume, and 24h price changes.

    Configuration is loaded from Django settings:
    - COINGECKO_BASE_URL
    - COINGECKO_TIMEOUT
    - COINGECKO_API_KEY (optional, for Pro tier)
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: Optional[int] = None):
        """
        Initialize CoinGecko client.

        Args:
            api_key: Optional API key (defaults to settings.COINGECKO_API_KEY)
            base_url: Optional base URL (defaults to settings.COINGECKO_BASE_URL)
            timeout: Optional timeout in seconds (defaults to settings.COINGECKO_TIMEOUT)
        """
        self.api_key = api_key or getattr(settings, "COINGECKO_API_KEY", "")
        self.base_url = base_url or getattr(settings, "COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3")
        self.timeout = timeout or getattr(settings, "COINGECKO_TIMEOUT", 10)

    def _get_headers(self) -> Dict[str, str]:
        """
        Get headers for API requests including authentication.

        Returns:
            Dictionary with headers including API key if configured
        """
        headers = {}
        if self.api_key:
            # Use Pro API header for pro-api subdomain, Demo header otherwise
            if "pro-api.coingecko.com" in self.base_url:
                headers["x-cg-pro-api-key"] = self.api_key
            else:
                headers["x-cg-demo-api-key"] = self.api_key
        return headers

    def fetch_prices(self, coin_ids: List[str]) -> Dict[str, Any]:
        """
        Fetch current prices for multiple cryptocurrencies.

        Args:
            coin_ids: List of CoinGecko coin IDs (e.g., ["bitcoin", "ethereum"])

        Returns:
            Dictionary mapping coin IDs to price data:
            {
                "bitcoin": {
                    "usd": 85940.00,
                    "usd_market_cap": 1700000000000,
                    "usd_24h_vol": 45000000000,
                    "usd_24h_change": 2.5
                },
                ...
            }

        Raises:
            requests.RequestException: If API request fails
        """
        if not coin_ids:
            return {}

        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        }

        try:
            response = requests.get(
                f"{self.base_url}/simple/price",
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"{LoggingContext.ASSETS} CoinGecko API error: {str(e)}")
            raise

    def get_coin_info(self, coin_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a cryptocurrency.

        Args:
            coin_id: CoinGecko coin ID (e.g., "bitcoin")

        Returns:
            Dictionary with detailed coin information including:
            - name, symbol, description
            - market data
            - contract addresses
            - community data

        Raises:
            requests.RequestException: If API request fails
        """
        try:
            response = requests.get(
                f"{self.base_url}/coins/{coin_id}",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"{LoggingContext.ASSETS} CoinGecko API error: {str(e)}")
            raise

    def fetch_prices_by_symbols(self, symbol_map: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch prices using a symbol-to-ID mapping.

        Args:
            symbol_map: Mapping of symbols to CoinGecko IDs
                Example: {"BTC": "bitcoin", "ETH": "ethereum"}

        Returns:
            Dictionary mapping symbols to price data:
            {
                "BTC": {
                    "price": "85940.00",
                    "market_cap": 1700000000000,
                    "24h_volume": 45000000000,
                    "24h_change": 2.5
                },
                ...
            }

        Raises:
            requests.RequestException: If API request fails
        """
        if not symbol_map:
            return {}

        # Fetch data using CoinGecko IDs
        coin_ids = list(symbol_map.values())
        api_data = self.fetch_prices(coin_ids)

        # Map back to symbols
        result = {}
        for symbol, coin_id in symbol_map.items():
            if coin_id in api_data and "usd" in api_data[coin_id]:
                coin_data = api_data[coin_id]
                result[symbol] = {
                    "price": str(Decimal(str(coin_data["usd"]))),
                    "market_cap": coin_data.get("usd_market_cap"),
                    "24h_volume": coin_data.get("usd_24h_vol"),
                    "24h_change": coin_data.get("usd_24h_change"),
                }

        return result

    def fetch_exchange_rate(self, target_currency: str = "aud") -> Optional[Decimal]:
        """
        Fetch the USD to target currency exchange rate using a stablecoin price.

        Uses USDT (tether) price in the target currency as a proxy for USD rate.

        Args:
            target_currency: Target currency code (e.g., "aud")

        Returns:
            Exchange rate as Decimal, or None if unavailable
        """
        params = {
            "ids": "tether",
            "vs_currencies": target_currency.lower(),
        }

        try:
            response = requests.get(
                f"{self.base_url}/simple/price",
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            rate = data.get("tether", {}).get(target_currency.lower())
            if rate is not None:
                return Decimal(str(rate))

            return None

        except requests.RequestException as e:
            logger.error(
                f"{LoggingContext.ASSETS} CoinGecko exchange rate error " f"(USD→{target_currency.upper()}): {str(e)}"
            )
            return None

    def fetch_historical_price(self, coin_id: str, timestamp: datetime) -> Optional[Decimal]:
        """
        Fetch historical price for a cryptocurrency at a specific timestamp.

        Uses CoinGecko's /coins/{id}/market_chart/range endpoint to get
        price data around the specified timestamp.

        Args:
            coin_id: CoinGecko coin ID (e.g., "bitcoin", "ethereum")
            timestamp: The datetime to fetch price for

        Returns:
            Price in USD as Decimal, or None if not available

        Raises:
            requests.RequestException: If API request fails
        """
        # Convert timestamp to unix time (seconds since epoch)
        from_timestamp = int(timestamp.timestamp())
        # Get data for +/- 1 hour window to ensure we get a data point
        to_timestamp = from_timestamp + 3600  # 1 hour after

        params = {
            "vs_currency": "usd",
            "from": from_timestamp,
            "to": to_timestamp,
        }

        try:
            response = requests.get(
                f"{self.base_url}/coins/{coin_id}/market_chart/range",
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            # Extract price data (returns array of [timestamp, price])
            prices = data.get("prices", [])
            if not prices:
                logger.warning(f"{LoggingContext.ASSETS} No historical price data for " f"{coin_id} at {timestamp}")
                return None

            # Get the first price (closest to our timestamp)
            price_usd = prices[0][1]
            return Decimal(str(price_usd))

        except requests.RequestException as e:
            logger.error(
                f"{LoggingContext.ASSETS} CoinGecko historical price error for " f"{coin_id} at {timestamp}: {str(e)}"
            )
            raise

    def fetch_historical_prices_bulk(
        self, coin_id: str, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical prices for a date range.

        Uses /market_chart with days parameter (Demo API compatible).
        Falls back to /market_chart/range for Pro API users.

        Args:
            coin_id: CoinGecko coin ID
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of price data points:
            [
                {"timestamp": datetime, "price": Decimal},
                ...
            ]

        Raises:
            requests.RequestException: If API request fails
        """
        # Calculate days between dates
        days = (end_date - start_date).days

        # Demo API supports /market_chart with days parameter (max 365 days)
        # Try this first as it works for both Demo and Pro plans
        if days <= 365:
            params = {
                "vs_currency": "usd",
                "days": str(days),
            }

            try:
                response = requests.get(
                    f"{self.base_url}/coins/{coin_id}/market_chart",
                    params=params,
                    headers=self._get_headers(),
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

                # Convert to list of dicts with timestamp and price
                prices = data.get("prices", [])
                result = []

                for price_data in prices:
                    timestamp_ms = price_data[0]
                    price_usd = price_data[1]

                    result.append(
                        {
                            "timestamp": datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                            "price": Decimal(str(price_usd)),
                        }
                    )

                logger.info(
                    f"{LoggingContext.ASSETS} Fetched {len(result)} historical prices for "
                    f"{coin_id} from {start_date} to {end_date} using /market_chart"
                )

                return result

            except requests.RequestException as e:
                # If days-based approach fails, fall through to range-based approach
                logger.warning(f"{LoggingContext.ASSETS} /market_chart failed, trying /market_chart/range: {str(e)}")

        # Fall back to /market_chart/range (Pro API only, or if days > 365)
        from_timestamp = int(start_date.timestamp())
        to_timestamp = int(end_date.timestamp())

        params = {
            "vs_currency": "usd",
            "from": from_timestamp,
            "to": to_timestamp,
        }

        try:
            response = requests.get(
                f"{self.base_url}/coins/{coin_id}/market_chart/range",
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            # Convert to list of dicts with timestamp and price
            prices = data.get("prices", [])
            result = []

            for price_data in prices:
                timestamp_ms = price_data[0]
                price_usd = price_data[1]

                result.append(
                    {
                        "timestamp": datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                        "price": Decimal(str(price_usd)),
                    }
                )

            logger.info(
                f"{LoggingContext.ASSETS} Fetched {len(result)} historical prices for "
                f"{coin_id} from {start_date} to {end_date} using /market_chart/range"
            )

            return result

        except requests.RequestException as e:
            logger.error(
                f"{LoggingContext.ASSETS} CoinGecko bulk historical price error for "
                f"{coin_id} ({start_date} to {end_date}): {str(e)}"
            )
            raise
