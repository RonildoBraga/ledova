from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from django.utils import timezone

from assets.models import AssetSnapshot
from portfolios.models import Portfolio
from shared.utils.datetime_utils import parse_end_date_inclusive
from wallets.models import HoldingSnapshot


def portfolio_value_series(
    portfolio: Portfolio, start_date: Optional[date] = None, end_date: Optional[date] = None
) -> list[dict[str, Any]]:
    last = min(end_date, timezone.now().date()) if end_date else timezone.now().date()
    wallets = list(portfolio.account_wallets())
    holding_rows = list(
        HoldingSnapshot.objects.filter(
            holding__wallet__in=wallets,
            holding__asset__is_active=True,
            holding__asset__is_verified=True,
            snapshot_date__lte=last,
        )
        .select_related("holding__asset")
        .order_by("snapshot_date")
    )
    if not holding_rows:
        return []
    first = max(start_date, holding_rows[0].snapshot_date) if start_date else holding_rows[0].snapshot_date
    if first > last:
        return []
    price_rows = list(
        AssetSnapshot.objects.filter(
            asset_id__in={row.holding.asset_id for row in holding_rows},
            source_timestamp__lt=parse_end_date_inclusive(last),
        ).order_by("source_timestamp")
    )

    computed_at = timezone.now()
    quantities: dict[tuple, Decimal] = {}
    assets: dict = {}
    prices: dict = {}
    points = []
    holding_index = price_index = 0
    day = holding_rows[0].snapshot_date
    while day <= last:
        while holding_index < len(holding_rows) and holding_rows[holding_index].snapshot_date == day:
            row = holding_rows[holding_index]
            quantities[(row.holding.wallet_id, row.holding.asset_id)] = row.quantity
            assets[row.holding.asset_id] = row.holding.asset
            holding_index += 1
        end_of_day = parse_end_date_inclusive(day)
        while price_index < len(price_rows) and price_rows[price_index].source_timestamp < end_of_day:
            prices[price_rows[price_index].asset_id] = price_rows[price_index]
            price_index += 1
        if day >= first:
            points.append(_point(portfolio, day, wallets, quantities, assets, prices, computed_at))
        day += timedelta(days=1)
    return points


def _point(portfolio, day, wallets, quantities, assets, prices, computed_at) -> dict[str, Any]:
    aggregated: dict[str, dict] = {}
    for wallet in wallets:
        for (wallet_id, asset_id), quantity in sorted(quantities.items()):
            if wallet_id != wallet.pk:
                continue
            asset = assets[asset_id]
            entry = aggregated.setdefault(asset.symbol, {"asset": asset, "quantity": Decimal("0"), "wallets": []})
            entry["quantity"] += quantity
            entry["wallets"].append(str(wallet.uuid))

    holdings_data = {}
    total_value = Decimal("0")
    for symbol, entry in aggregated.items():
        holdings_data[symbol] = {
            "asset_uuid": str(entry["asset"].uuid),
            "quantity": str(entry["quantity"]),
            "wallets": entry["wallets"],
        }
        price = prices.get(entry["asset"].pk)
        if price is not None:
            market_value = entry["quantity"] * price.price
            total_value += market_value
            holdings_data[symbol]["price"] = str(price.price)
            holdings_data[symbol]["market_value"] = str(market_value)
    total = total_value if total_value > 0 else None

    return {
        "uuid": f"{portfolio.uuid}:{day.isoformat()}",
        "portfolio": portfolio.uuid,
        "portfolio_name": portfolio.name,
        "account_id": str(portfolio.user_account_id),
        "holdings_data": holdings_data,
        "total_market_value": total,
        "has_value_data": total is not None,
        "snapshot_date": day,
        "snapshot_reason": "DAILY",
        "created_at": computed_at,
        "updated_at": computed_at,
    }
