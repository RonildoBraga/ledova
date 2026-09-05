import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from assets.models import Asset, AssetSnapshot
from assets.services.identity import native_asset_for_chain, quarantine_unknown_token
from compliance.services.transaction_monitoring import TransactionMonitoringService
from integrations.blockchain import get_blockchain_client
from shared.constants import normalize_chain
from wallets.constants import SNAPSHOT_REASON_DAILY, SNAPSHOT_REASON_TRANSACTION
from wallets.models import Holding, HoldingSnapshot, Transaction, Wallet
from wallets.services.chain import fetch_chain_balance

logger = logging.getLogger(__name__)


class WalletSyncService:

    @staticmethod
    def sync_wallet(wallet: Wallet) -> Dict[str, Any]:
        if not wallet.is_verified:
            return {"status": "skipped", "error": "Wallet not verified"}

        try:
            chain = normalize_chain(wallet.chain)
            transactions_data = get_blockchain_client(chain).get_transaction_history(wallet.address)
            for tx in transactions_data:
                # _process_single_transaction reads tx["chain"]; the client payload has no chain key.
                tx["chain"] = chain

            result = WalletSyncService._process_transactions(wallet, transactions_data)

            holdings_updated = WalletSyncService._sync_holdings_from_blockchain(wallet)
            result["holdings"] = holdings_updated

            wallet.last_synced_at = timezone.now()
            wallet.save(update_fields=["last_synced_at"])

            return result

        except Exception as e:
            logger.error(f"Error: {e.__class__.__name__}: {e}")
            return {"status": "error", "error": f"{e.__class__.__name__}: {str(e)}"}

    @staticmethod
    def _process_transactions(wallet: Wallet, transactions_data: List[Dict]) -> Dict[str, Any]:
        transactions_created = 0
        snapshots_created = 0

        with transaction.atomic():
            for tx_data in transactions_data:
                try:
                    result = WalletSyncService._process_single_transaction(wallet, tx_data)

                    if result["tx"]:
                        transactions_created += 1
                    if result["snapshot"]:
                        snapshots_created += 1

                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipped tx: {e}")
                    continue

        return {
            "status": "success",
            "transactions": transactions_created,
            "snapshots": snapshots_created,
        }

    @staticmethod
    def _process_single_transaction(wallet: Wallet, tx_data: Dict) -> Dict[str, bool]:
        result = {"tx": False, "snapshot": False}
        asset = WalletSyncService._resolve_asset(wallet, tx_data)

        block_timestamp = tx_data["block_timestamp"]
        if isinstance(block_timestamp, str):
            block_timestamp = parse_datetime(block_timestamp)
        amount = Decimal(str(tx_data["amount"]))
        market_value = WalletSyncService._calculate_market_value(amount, asset, block_timestamp)

        tx, created = Transaction.objects.update_or_create(
            tx_hash=tx_data["tx_hash"],
            wallet=wallet,
            defaults={
                "chain": tx_data["chain"].lower(),
                "from_address": tx_data["from_address"],
                "to_address": tx_data["to_address"],
                "asset": asset,
                "amount": tx_data["amount"],
                "market_value": market_value,
                "block_timestamp": block_timestamp,
                "block_number": tx_data.get("block_number"),
                "transaction_fee": tx_data.get("transaction_fee"),
                "status": tx_data.get("status", "success"),
            },
        )
        result["tx"] = created
        if created:
            TransactionMonitoringService.check_new_transaction(tx)

        if created and asset.is_verified:
            holding, _ = Holding.objects.get_or_create(
                wallet=wallet,
                asset=asset,
                defaults={"quantity": Decimal("0")},
            )
            snapshot_date = block_timestamp.date() if block_timestamp else timezone.now().date()
            if snapshot_date == timezone.now().date():
                _, snapshot_created = HoldingSnapshot.objects.update_or_create(
                    holding=holding,
                    snapshot_date=snapshot_date,
                    defaults={
                        "quantity": holding.quantity,
                        "block_number": tx_data.get("block_number"),
                        "snapshot_reason": SNAPSHOT_REASON_TRANSACTION,
                        "caused_by_transaction": tx,
                    },
                )
                result["snapshot"] = snapshot_created
        elif created and not asset.is_verified:
            logger.info(f"Skipping holding for unverified asset: {asset.symbol} (tx recorded for audit)")

        return result

    @staticmethod
    def _resolve_asset(wallet: Wallet, tx_data: Dict) -> Asset:
        """Identity is (chain, contract address), never the self-declared symbol; an unknown contract is quarantined."""
        contract_address = tx_data.get("contract_address")
        if not contract_address:
            return native_asset_for_chain(wallet.chain)
        asset = Asset.get_by_chain_and_contract(wallet.chain, contract_address)
        if asset is None:
            asset = quarantine_unknown_token(
                chain=wallet.chain,
                contract_address=contract_address,
                symbol=tx_data.get("asset_symbol", tx_data.get("asset")),
                decimals=tx_data.get("token_decimals"),
            )
        return asset

    @staticmethod
    def _sync_holdings_from_blockchain(wallet: Wallet) -> int:
        updated = 0

        for holding in wallet.holdings.select_related("asset").filter(asset__is_verified=True):
            blockchain_balance = fetch_chain_balance(wallet, holding.asset)

            if blockchain_balance is not None:
                holding.quantity = blockchain_balance
                holding.last_synced_at = timezone.now()
                holding.save(update_fields=["quantity", "last_synced_at"])
                updated += 1

                # One row per holding per day, so a wallet with no transactions still has a daily series.
                HoldingSnapshot.objects.update_or_create(
                    holding=holding,
                    snapshot_date=timezone.now().date(),
                    defaults={"quantity": blockchain_balance},
                    create_defaults={"quantity": blockchain_balance, "snapshot_reason": SNAPSHOT_REASON_DAILY},
                )

        return updated

    @staticmethod
    def _calculate_market_value(amount: Decimal, asset: Asset, timestamp: datetime) -> Optional[Decimal]:
        if not timestamp:
            return None

        try:
            price = AssetSnapshot.objects.filter(asset=asset).get_price_at_timestamp(timestamp)
            if price is not None:
                market_value = abs(amount) * price
                return market_value.quantize(Decimal("0.01"))
            return None
        except Exception as e:
            logger.warning(f"Failed to calculate market value for {asset.symbol}: {e}")
            return None
