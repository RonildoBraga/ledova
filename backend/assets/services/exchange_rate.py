import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction

from assets.models import ExchangeRate
from integrations.coingecko import CoinGeckoClient
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")

SUPPORTED_TARGET_CURRENCIES = ["AUD"]


class ExchangeRateService:

    @staticmethod
    def sync_exchange_rates() -> dict:
        """Fetch and store exchange rates for all supported target currencies."""
        client = CoinGeckoClient()
        updated = 0

        for currency in SUPPORTED_TARGET_CURRENCIES:
            rate = client.fetch_exchange_rate(target_currency=currency.lower())
            if rate is None:
                logger.warning(f"{LoggingContext.ASSETS} Could not fetch exchange rate for USD→{currency}")
                continue

            with transaction.atomic():
                ExchangeRate.objects.update_or_create(
                    base_currency="USD",
                    target_currency=currency,
                    defaults={"rate": rate},
                )

            logger.info(f"{LoggingContext.ASSETS} Updated exchange rate USD→{currency}: {rate}")
            updated += 1

        return {"updated": updated, "total": len(SUPPORTED_TARGET_CURRENCIES)}

    @staticmethod
    def get_rate(base_currency: str = "USD", target_currency: str = "AUD") -> Optional[Decimal]:
        """Get the stored exchange rate for a currency pair."""
        if base_currency == target_currency:
            return Decimal("1")

        try:
            exchange_rate = ExchangeRate.objects.get(
                base_currency=base_currency,
                target_currency=target_currency,
            )
            return exchange_rate.rate
        except ExchangeRate.DoesNotExist:
            return None
