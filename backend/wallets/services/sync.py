import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from assets.models import Asset, AssetSnapshot
from compliance.services.transaction_monitoring import TransactionMonitoringService
from integrations.blockchain import get_blockchain_client
from shared.constants import normalize_chain
from shared.utils.logging_utils import LoggingContext
from wallets.constants import SNAPSHOT_REASON_TRANSACTION
from wallets.models import Holding, HoldingSnapshot, Transaction, Wallet
from wallets.services.chain import fetch_chain_balance
from wallets.utils.scam_detection import is_scam_token

logger = logging.getLogger("ledova_backend")


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
            logger.error(f"{LoggingContext.WALLET_SYNC} Error: {e.__class__.__name__}: {e}")
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
                    logger.warning(f"{LoggingContext.WALLET_SYNC} Skipped tx: {e}")
                    continue

        return {
            "status": "success",
            "transactions": transactions_created,
            "snapshots": snapshots_created,
        }

    @staticmethod
    def _process_single_transaction(wallet: Wallet, tx_data: Dict) -> Dict[str, bool]:
        result = {"tx": False, "snapshot": False}

        asset_symbol = tx_data.get("asset_symbol", tx_data.get("asset", "UNKNOWN"))
        contract_address = tx_data.get("contract_address")
        token_decimals = tx_data.get("token_decimals")
        category = tx_data.get("category", "external")

        scam_result = is_scam_token(asset_symbol, contract_address)
        if scam_result.is_scam:
            impersonating = f" (impersonating {scam_result.matched_token})" if scam_result.matched_token else ""
            logger.warning(
                f"{LoggingContext.WALLET_SYNC} Skipping potential scam token: "
                f"'{asset_symbol}' (contract: {contract_address or 'N/A'}) - "
                f"{scam_result.reason}{impersonating}"
            )
            return result

        if contract_address and category == "erc20":
            asset = Asset.get_by_chain_and_contract(wallet.chain, contract_address)
            if asset:
                logger.debug(
                    f"{LoggingContext.WALLET_SYNC} Found ERC-20 asset by contract: "
                    f"{asset.symbol} ({contract_address[:10]}...)"
                )
            else:
                asset, created = Asset.objects.get_or_create(
                    symbol=asset_symbol,
                    defaults={
                        "name": asset_symbol,
                        "asset_type": "erc20_token",
                        "decimals": token_decimals or 18,
                    },
                )
                if created:
                    from assets.models import AssetChainDeployment

                    AssetChainDeployment.objects.get_or_create(
                        asset=asset,
                        chain=wallet.chain,
                        defaults={
                            "contract_address": contract_address,
                            "decimals": token_decimals or 18,
                        },
                    )
                logger.info(
                    f"{LoggingContext.WALLET_SYNC} {'Created' if created else 'Found'} ERC-20 asset: "
                    f"{asset_symbol} ({contract_address[:10]}...)"
                )
        else:
            asset, _ = Asset.objects.get_or_create(
                symbol=asset_symbol,
                defaults={
                    "name": asset_symbol,
                    "asset_type": "native_crypto",
                },
            )

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
            logger.info(
                f"{LoggingContext.WALLET_SYNC} Skipping holding for unverified asset: "
                f"{asset.symbol} (tx recorded for audit)"
            )

        return result

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

                today = timezone.now().date()
                HoldingSnapshot.objects.filter(holding=holding, snapshot_date=today).update(quantity=blockchain_balance)

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
            logger.warning(f"{LoggingContext.WALLET_SYNC} Failed to calculate market value for {asset.symbol}: {e}")
            return None
