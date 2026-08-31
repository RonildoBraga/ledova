import logging
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain import BaseChainClient, get_base_chain_client
from integrations.base_chain.exceptions import (
    BaseChainContractError,
    BaseChainTransactionError,
)
from shared.utils.logging_utils import LoggingContext
from wallets.models import Wallet
from whitelist.exceptions import (
    AddressAlreadyWhitelistedException,
    AddressNotWhitelistedException,
    WhitelistContractNotConfiguredException,
    WhitelistOperationFailedException,
)
from whitelist.models import WhitelistEntry, WhitelistStatus

logger = logging.getLogger(__name__)


class WhitelistService:
    def __init__(
        self,
        contract_address: Optional[str] = None,
        signer_key: Optional[str] = None,
    ):
        self.chain_client: BaseChainClient = get_base_chain_client()
        self.contract_address = contract_address or getattr(settings, "WHITELIST_CONTRACT_ADDRESS", None)
        self.signer_key = signer_key or getattr(settings, "BLOCKCHAIN_OPERATOR_KEY", None)
        self._contract = None

    @property
    def contract(self):
        if self._contract is None:
            if not self.contract_address:
                raise WhitelistContractNotConfiguredException(
                    "Whitelist contract address not configured. Set WHITELIST_CONTRACT_ADDRESS in settings."
                )
            self._contract = self.chain_client.load_contract("WhitelistRegistry", self.contract_address)
        return self._contract

    @property
    def signer_address(self) -> str:
        if not self.signer_key:
            raise WhitelistContractNotConfiguredException(
                "Blockchain operator key not configured. Set BLOCKCHAIN_OPERATOR_KEY in environment."
            )
        account = self.chain_client.account_from_key(self.signer_key)
        return account.address

    def is_whitelisted(self, address: str) -> bool:
        checksum_address = self.chain_client.to_checksum_address(address)
        return self.contract.functions.isWhitelisted(checksum_address).call()

    def get_investor_info(self, address: str) -> dict:
        checksum_address = self.chain_client.to_checksum_address(address)
        result = self.contract.functions.getInvestorInfo(checksum_address).call()
        return {
            "whitelisted": result[0],
            "kyc_timestamp": result[1],
        }

    def get_whitelist_count(self) -> int:
        return self.contract.functions.whitelistCount().call()

    def can_receive(self, address: str) -> bool:
        checksum_address = self.chain_client.to_checksum_address(address)
        return self.contract.functions.canReceive(checksum_address).call()

    def get_receive_eligibility(self, address: str) -> dict:
        checksum_address = self.chain_client.to_checksum_address(address)
        db_whitelisted = WhitelistEntry.objects.filter_by_address(checksum_address).active().exists()

        on_chain_whitelisted = None
        try:
            on_chain_whitelisted = self.is_whitelisted(checksum_address)
        except Exception as e:
            logger.warning(f"{LoggingContext.WHITELIST} Failed to check on-chain status for {address}: {e}")

        return {
            "can_receive": db_whitelisted or (on_chain_whitelisted is True),
            "db_whitelisted": db_whitelisted,
            "on_chain_whitelisted": on_chain_whitelisted,
        }

    def _get_or_create_investor_wallet(self, address: str) -> Wallet:
        checksum_address = self.chain_client.to_checksum_address(address)
        wallet = Wallet.objects.filter_by_address(checksum_address).first()
        if wallet:
            return wallet
        return Wallet.objects.create(
            address=checksum_address,
            is_verified=True,
            verified_at=timezone.now(),
        )

    @staticmethod
    def is_address_whitelisted(address: str) -> bool:
        return WhitelistEntry.objects.filter_by_address(address).active().exists()

    @transaction.atomic
    def add_to_whitelist(
        self,
        address: str,
        wait_for_receipt: bool = True,
    ) -> tuple[str, Optional[WhitelistEntry]]:
        if not self.signer_key:
            raise WhitelistContractNotConfiguredException("Blockchain operator key not configured")

        checksum_address = self.chain_client.to_checksum_address(address)

        if self.is_whitelisted(address):
            raise AddressAlreadyWhitelistedException(f"Address {address} is already whitelisted")

        wallet = self._get_or_create_investor_wallet(checksum_address)

        entry, created = WhitelistEntry.objects.get_or_create(
            wallet=wallet,
            defaults={"status": WhitelistStatus.PENDING},
        )

        tx_record = BlockchainTransaction.objects.create(
            tx_type=TransactionType.WHITELIST_ADD,
            status=TransactionStatus.PENDING,
            from_address=self.signer_address,
            to_address=self.contract_address,
            function_name="addToWhitelist",
            function_args={"investor": checksum_address},
            related_model="whitelist.WhitelistEntry",
            related_uuid=entry.uuid,
        )

        try:
            contract_function = self.contract.functions.addToWhitelist(checksum_address)
            tx_hash, receipt = self.chain_client.send_transaction(
                contract_function,
                self.signer_key,
                wait_for_receipt=wait_for_receipt,
            )

            tx_record.mark_submitted(tx_hash)

            if receipt:
                tx_record.mark_confirmed(
                    block_number=receipt["blockNumber"],
                    block_hash=receipt["blockHash"].hex(),
                    gas_used=receipt["gasUsed"],
                )
                entry.mark_active(tx_hash)

            logger.info(f"{LoggingContext.WHITELIST} Added {checksum_address} to whitelist (tx={tx_hash})")
            return tx_hash, entry

        except (BaseChainTransactionError, BaseChainContractError) as e:
            tx_record.mark_failed(str(e))
            entry.mark_failed(str(e))
            logger.error(f"{LoggingContext.WHITELIST} Failed to add {address}: {e}")
            raise WhitelistOperationFailedException(f"Failed to add to whitelist: {e}") from e

    @transaction.atomic
    def remove_from_whitelist(
        self,
        address: str,
        wait_for_receipt: bool = True,
    ) -> tuple[str, Optional[WhitelistEntry]]:
        if not self.signer_key:
            raise WhitelistContractNotConfiguredException("Blockchain operator key not configured")

        checksum_address = self.chain_client.to_checksum_address(address)

        if not self.is_whitelisted(address):
            raise AddressNotWhitelistedException(f"Address {address} is not whitelisted")

        entry = WhitelistEntry.objects.filter_by_address(checksum_address).first()

        tx_record = BlockchainTransaction.objects.create(
            tx_type=TransactionType.WHITELIST_REMOVE,
            status=TransactionStatus.PENDING,
            from_address=self.signer_address,
            to_address=self.contract_address,
            function_name="removeFromWhitelist",
            function_args={"investor": checksum_address},
            related_model="whitelist.WhitelistEntry" if entry else None,
            related_uuid=entry.uuid if entry else None,
        )

        try:
            contract_function = self.contract.functions.removeFromWhitelist(checksum_address)
            tx_hash, receipt = self.chain_client.send_transaction(
                contract_function,
                self.signer_key,
                wait_for_receipt=wait_for_receipt,
            )

            tx_record.mark_submitted(tx_hash)

            if receipt:
                tx_record.mark_confirmed(
                    block_number=receipt["blockNumber"],
                    block_hash=receipt["blockHash"].hex(),
                    gas_used=receipt["gasUsed"],
                )
                if entry:
                    entry.mark_removed(tx_hash)

            logger.info(f"{LoggingContext.WHITELIST} Removed {checksum_address} from whitelist (tx={tx_hash})")
            return tx_hash, entry

        except (BaseChainTransactionError, BaseChainContractError) as e:
            tx_record.mark_failed(str(e))
            if entry:
                entry.mark_failed(str(e))
            logger.error(f"{LoggingContext.WHITELIST} Failed to remove {address}: {e}")
            raise WhitelistOperationFailedException(f"Failed to remove from whitelist: {e}") from e

    @transaction.atomic
    def sync_entry(self, address: str) -> WhitelistEntry:
        checksum_address = self.chain_client.to_checksum_address(address)
        info = self.get_investor_info(address)
        wallet = self._get_or_create_investor_wallet(checksum_address)

        kyc_ts = info["kyc_timestamp"]
        on_chain_ts = datetime.fromtimestamp(kyc_ts, tz=dt_timezone.utc) if kyc_ts else None

        entry, created = WhitelistEntry.objects.update_or_create(
            wallet=wallet,
            defaults={
                "is_whitelisted": info["whitelisted"],
                "on_chain_timestamp": on_chain_ts,
                "status": WhitelistStatus.ACTIVE if info["whitelisted"] else WhitelistStatus.REMOVED,
                "last_synced_at": timezone.now(),
            },
        )

        logger.debug(f"{LoggingContext.WHITELIST} Synced {checksum_address}: {info}")
        return entry

    def sync_entries(self, entries: list[WhitelistEntry]) -> dict:
        synced = 0
        errors = []

        for entry in entries:
            try:
                self.sync_entry(entry.wallet.address)
                synced += 1
            except Exception as e:
                errors.append(f"Failed to sync {entry.wallet.address}: {e}")
                logger.error(f"{LoggingContext.WHITELIST} Failed to sync {entry.wallet.address}: {e}")

        return {"synced": synced, "errors": errors}

    def sync_all_entries(self) -> int:
        entries = list(WhitelistEntry.objects.active() | WhitelistEntry.objects.pending())
        result = self.sync_entries(entries)
        logger.info(f"{LoggingContext.WHITELIST} Synced {result['synced']} entries")
        return result["synced"]

    def ensure_whitelisted(self, entries: list[WhitelistEntry]) -> dict:
        to_add = []
        to_sync = []
        skipped = 0
        errors = []

        for entry in entries:
            if entry.is_whitelisted:
                skipped += 1
                continue
            try:
                if self.is_whitelisted(entry.wallet.address):
                    to_sync.append(entry)
                else:
                    to_add.append(entry)
            except Exception as e:
                errors.append(f"Failed to check {entry.wallet.address}: {e}")
                logger.error(f"{LoggingContext.WHITELIST} Failed to check {entry.wallet.address}: {e}")

        for entry in to_sync:
            try:
                self.sync_entry(entry.wallet.address)
            except Exception as e:
                errors.append(f"Failed to sync {entry.wallet.address}: {e}")
                logger.error(f"{LoggingContext.WHITELIST} Failed to sync {entry.wallet.address}: {e}")

        if to_add:
            addresses = [entry.wallet.address for entry in to_add]
            try:
                tx_hash = self.batch_add_to_whitelist(addresses, wait_for_receipt=True)
                logger.info(f"{LoggingContext.WHITELIST} Batch added {len(addresses)} addresses (tx={tx_hash})")
                for entry in to_add:
                    try:
                        self.sync_entry(entry.wallet.address)
                    except Exception as e:
                        errors.append(f"Failed to sync {entry.wallet.address} after add: {e}")
                        logger.error(f"{LoggingContext.WHITELIST} Post-add sync failed for {entry.wallet.address}: {e}")
            except Exception as e:
                errors.append(f"Batch add failed: {e}")
                logger.error(f"{LoggingContext.WHITELIST} Batch add failed: {e}")

        return {
            "added": len(to_add),
            "synced": len(to_sync),
            "skipped": skipped,
            "errors": errors,
        }

    def ensure_removed(self, entries: list[WhitelistEntry]) -> dict:
        removed = 0
        skipped = 0
        errors = []

        for entry in entries:
            if not entry.is_whitelisted:
                skipped += 1
                continue
            try:
                self.remove_from_whitelist(address=entry.wallet.address, wait_for_receipt=True)
                removed += 1
            except AddressNotWhitelistedException:
                self.sync_entry(entry.wallet.address)
                removed += 1
            except Exception as e:
                errors.append(f"Failed to remove {entry.wallet.address}: {e}")
                logger.error(f"{LoggingContext.WHITELIST} Failed to remove {entry.wallet.address}: {e}")

        return {
            "removed": removed,
            "skipped": skipped,
            "errors": errors,
        }

    def batch_add_to_whitelist(
        self,
        addresses: list[str],
        wait_for_receipt: bool = True,
    ) -> str:
        if not self.signer_key:
            raise WhitelistContractNotConfiguredException("Blockchain operator key not configured")

        checksum_addresses = [self.chain_client.to_checksum_address(addr) for addr in addresses]

        try:
            contract_function = self.contract.functions.batchAddToWhitelist(checksum_addresses)
            tx_hash, receipt = self.chain_client.send_transaction(
                contract_function,
                self.signer_key,
                wait_for_receipt=wait_for_receipt,
            )
            logger.info(f"{LoggingContext.WHITELIST} Batch added {len(addresses)} addresses (tx={tx_hash})")
            return tx_hash

        except (BaseChainTransactionError, BaseChainContractError) as e:
            logger.error(f"{LoggingContext.WHITELIST} Batch add failed: {e}")
            raise WhitelistOperationFailedException(f"Batch add failed: {e}") from e
