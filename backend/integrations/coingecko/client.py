"""CoinGecko market-data client. Free tier: no key, 10-50 calls/minute, https://api.coingecko.com/api/v3."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class CoinGeckoClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: Optional[int] = None):
        self.api_key = api_key or getattr(settings, "COINGECKO_API_KEY", "")
        self.base_url = base_url or getattr(settings, "COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3")
        self.timeout = timeout or getattr(settings, "COINGECKO_TIMEOUT", 10)

    def _get_headers(self) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            # Use Pro API header for pro-api subdomain, Demo header otherwise
            if "pro-api.coingecko.com" in self.base_url:
                headers["x-cg-pro-api-key"] = self.api_key
            else:
                headers["x-cg-demo-api-key"] = self.api_key
        return headers

    def fetch_prices(self, coin_ids: List[str]) -> Dict[str, Any]:
        """Prices keyed by CoinGecko coin id.

        {"bitcoin": {"usd", "usd_market_cap", "usd_24h_vol", "usd_24h_change"}}
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
            logger.error(f"CoinGecko API error: {str(e)}")
            raise

    def fetch_prices_by_symbols(self, symbol_map: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """Prices keyed by symbol: {"BTC": {"price" (str), "market_cap", "24h_volume", "24h_change"}}."""
        if not symbol_map:
            return {}

        coin_ids = list(symbol_map.values())
        api_data = self.fetch_prices(coin_ids)

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
        """USD to target-currency rate, using the USDT price in that currency as the proxy."""
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
            logger.error(f"CoinGecko exchange rate error (USD→{target_currency.upper()}): {str(e)}")
            return None

    def fetch_historical_prices_bulk(
        self, coin_id: str, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Uses /market_chart?days= (Demo API) and falls back to /market_chart/range (Pro API)."""
        days = (end_date - start_date).days

        # Demo API supports /market_chart with days parameter (max 365 days)
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
                    f"Fetched {len(result)} historical prices for "
                    f"{coin_id} from {start_date} to {end_date} using /market_chart"
                )

                return result

            except requests.RequestException as e:
                logger.warning(f"/market_chart failed, trying /market_chart/range: {str(e)}")

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
                f"Fetched {len(result)} historical prices for "
                f"{coin_id} from {start_date} to {end_date} using /market_chart/range"
            )

            return result

        except requests.RequestException as e:
            logger.error(f"CoinGecko bulk historical price error for {coin_id} ({start_date} to {end_date}): {str(e)}")
            raise
