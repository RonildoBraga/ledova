import logging
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from django.utils import timezone

from assets.models import AssetType
from shared.db import atomic
from wallets.constants import SNAPSHOT_REASON_DAILY
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, HoldingSnapshot, Wallet, WalletSubmissionFamily
from wallets.services.chain import fetch_chain_balance
from wallets.services.family_balances import sync_family_balances

logger = logging.getLogger(__name__)


def _has_submission_family(wallet, asset):
    families = WalletSubmissionFamily.objects.filter(wallet=wallet)
    if asset.asset_type != AssetType.NATIVE_CRYPTO.value:
        families = families.filter(asset=asset)
    return families.exists()


def sync_holding(wallet, asset) -> Optional[Holding]:
    if _has_submission_family(wallet, asset):
        try:
            holdings = sync_family_balances(wallet, extra_asset_ids=[asset.pk])
        except InvalidTransactionException:
            return None
        return holdings.get(str(asset.pk)) if holdings is not None else None
    expected = Holding.objects.filter(wallet=wallet, asset=asset).values_list("uuid", "balance_version").first()
    balance = fetch_chain_balance(wallet, asset)
    if balance is None:
        logger.info(f"No chain balance for {asset.symbol} on {wallet.chain}; holding left untouched")
        return None

    with atomic():
        Wallet.objects.select_for_update().get(pk=wallet.pk)
        if _has_submission_family(wallet, asset):
            return None
        holding = Holding.objects.select_for_update().filter(wallet=wallet, asset=asset).first()
        actual = (holding.pk, holding.balance_version) if holding is not None else None
        if expected != actual:
            logger.info("Holding changed while its balance was being read; the stale observation was discarded")
            return None
        if holding is None:
            holding = Holding.objects.create(wallet=wallet, asset=asset, quantity=Decimal("0"))
        if holding.quantity != balance:
            logger.info(
                f"Corrected {asset.symbol} on {wallet.chain} "
                f"from {holding.quantity} to {balance} for wallet {wallet.uuid}"
            )
        holding.quantity = balance
        holding.last_synced_at = timezone.now()
        holding.sync_version = uuid4()
        holding.balance_version = holding.sync_version
        holding.save(update_fields=["quantity", "last_synced_at", "balance_version", "sync_version", "updated_at"])
        HoldingSnapshot.objects.update_or_create(
            holding=holding,
            snapshot_date=timezone.now().date(),
            defaults={"quantity": balance},
            create_defaults={"quantity": balance, "snapshot_reason": SNAPSHOT_REASON_DAILY},
        )
    return holding
