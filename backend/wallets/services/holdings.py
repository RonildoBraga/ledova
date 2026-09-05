import logging
from decimal import Decimal
from typing import Optional

from django.utils import timezone

from wallets.constants import SNAPSHOT_REASON_DAILY
from wallets.models import Holding, HoldingSnapshot
from wallets.services.chain import fetch_chain_balance

logger = logging.getLogger(__name__)


def sync_holding(wallet, asset) -> Optional[Holding]:
    balance = fetch_chain_balance(wallet, asset)
    if balance is None:
        logger.info(f"No chain balance for {asset.symbol} on {wallet.chain}; holding left untouched")
        return None

    holding, _ = Holding.objects.get_or_create(wallet=wallet, asset=asset, defaults={"quantity": Decimal("0")})
    holding.quantity = balance
    holding.last_synced_at = timezone.now()
    holding.save(update_fields=["quantity", "last_synced_at", "updated_at"])
    HoldingSnapshot.objects.update_or_create(
        holding=holding,
        snapshot_date=timezone.now().date(),
        defaults={"quantity": balance},
        create_defaults={"quantity": balance, "snapshot_reason": SNAPSHOT_REASON_DAILY},
    )
    return holding
