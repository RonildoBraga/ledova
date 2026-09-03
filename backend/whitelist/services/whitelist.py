import logging
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Optional

from django.conf import settings
from django.utils import timezone

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain import BaseChainClient, get_base_chain_client
from integrations.base_chain.exceptions import (
    BaseChainContractError,
    BaseChainTransactionError,
)
from wallets.models import Wallet
from whitelist.exceptions import (
    AddressAlreadyWhitelistedException,
    AddressNotWhitelistedException,
    WalletNotRegisteredException,
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

    # On-chain reads

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
            logger.warning(f"Failed to check on-chain status for {address}: {e}")

        return {
            "can_receive": db_whitelisted or (on_chain_whitelisted is True),
            "db_whitelisted": db_whitelisted,
            "on_chain_whitelisted": on_chain_whitelisted,
        }

    # Registry transactions

    @staticmethod
    def _resolve_wallet(checksum_address: str, wallet_uuid=None) -> Wallet:
        """The wallet behind an address; a uuid picks between duplicates, otherwise the match must be unique."""
        wallets = Wallet.objects.filter_by_address(checksum_address).order_by("uuid")
        if wallet_uuid is not None:
            wallet = wallets.filter(uuid=wallet_uuid).first()
        else:
            matches = list(wallets[:2])
            wallet = matches[0] if len(matches) == 1 else None
        if wallet is None:
            raise WalletNotRegisteredException()
        return wallet

    def _send_tx(self, tx_type, function_name, checksum_address, entry, wait_for_receipt):
        """Record, send and settle one registry call; a chain error marks the record and the entry failed."""
        tx_record = BlockchainTransaction.objects.create(
            tx_type=tx_type,
            status=TransactionStatus.PENDING,
            from_address=self.signer_address,
            to_address=self.contract_address,
            function_name=function_name,
            function_args={"investor": checksum_address},
            related_model="whitelist.WhitelistEntry" if entry else None,
            related_uuid=entry.uuid if entry else None,
        )
        try:
            contract_function = getattr(self.contract.functions, function_name)(checksum_address)
            tx_hash, receipt = self.chain_client.send_transaction(
                contract_function,
                self.signer_key,
                wait_for_receipt=wait_for_receipt,
            )
        except (BaseChainTransactionError, BaseChainContractError) as e:
            tx_record.mark_failed(str(e))
            if entry:
                entry.mark_failed(str(e))
            logger.error(f"{function_name}({checksum_address}) failed: {e}")
            raise WhitelistOperationFailedException(f"{TransactionType(tx_type).label} failed: {e}") from e

        tx_record.mark_submitted(tx_hash)
        if receipt:
            tx_record.mark_confirmed(
                block_number=receipt["blockNumber"],
                block_hash=receipt["blockHash"].hex(),
                gas_used=receipt["gasUsed"],
            )
        logger.info(f"{function_name}({checksum_address}) sent (tx={tx_hash})")
        return tx_hash, receipt

    def add_to_whitelist(
        self,
        address: str,
        wait_for_receipt: bool = True,
        wallet_uuid=None,
    ) -> tuple[str, WhitelistEntry]:
        checksum_address = self.chain_client.to_checksum_address(address)
        if self.is_whitelisted(checksum_address):
            raise AddressAlreadyWhitelistedException(f"Address {address} is already whitelisted")

        wallet = self._resolve_wallet(checksum_address, wallet_uuid)
        entry, _ = WhitelistEntry.objects.get_or_create(wallet=wallet, defaults={"status": WhitelistStatus.PENDING})
        tx_hash, receipt = self._send_tx(
            TransactionType.WHITELIST_ADD, "addToWhitelist", checksum_address, entry, wait_for_receipt
        )
        if receipt:
            entry.mark_active(tx_hash)
        return tx_hash, entry

    def remove_from_whitelist(
        self,
        address: str,
        wait_for_receipt: bool = True,
    ) -> tuple[str, Optional[WhitelistEntry]]:
        checksum_address = self.chain_client.to_checksum_address(address)
        if not self.is_whitelisted(checksum_address):
            raise AddressNotWhitelistedException(f"Address {address} is not whitelisted")

        entry = WhitelistEntry.objects.filter_by_address(checksum_address).first()
        tx_hash, receipt = self._send_tx(
            TransactionType.WHITELIST_REMOVE, "removeFromWhitelist", checksum_address, entry, wait_for_receipt
        )
        if receipt and entry:
            entry.mark_removed(tx_hash)
        return tx_hash, entry

    # Database sync

    def sync_entry(self, address: str, wallet_uuid=None) -> WhitelistEntry:
        checksum_address = self.chain_client.to_checksum_address(address)
        wallet = self._resolve_wallet(checksum_address, wallet_uuid)

        info = self.get_investor_info(checksum_address)
        kyc_ts = info["kyc_timestamp"]
        on_chain_ts = datetime.fromtimestamp(kyc_ts, tz=dt_timezone.utc) if kyc_ts else None

        entry, _ = WhitelistEntry.objects.update_or_create(
            wallet=wallet,
            defaults={
                "is_whitelisted": info["whitelisted"],
                "on_chain_timestamp": on_chain_ts,
                "status": WhitelistStatus.ACTIVE if info["whitelisted"] else WhitelistStatus.REMOVED,
                "last_synced_at": timezone.now(),
            },
        )

        logger.debug(f"Synced {checksum_address}: {info}")
        return entry

    def sync_entries(self, entries: list[WhitelistEntry]) -> dict:
        synced = 0
        errors = []

        for entry in entries:
            try:
                self.sync_entry(entry.wallet.address, wallet_uuid=entry.wallet_id)
                synced += 1
            except Exception as e:
                errors.append(f"Failed to sync {entry.wallet.address}: {e}")
                logger.error(f"Failed to sync {entry.wallet.address}: {e}")

        return {"synced": synced, "errors": errors}

    def sync_all_entries(self) -> int:
        entries = list(WhitelistEntry.objects.active() | WhitelistEntry.objects.pending())
        result = self.sync_entries(entries)
        logger.info(f"Synced {result['synced']} entries")
        return result["synced"]

    def ensure_whitelisted(self, entries: list[WhitelistEntry]) -> dict:
        result = {"added": 0, "synced": 0, "skipped": 0, "errors": []}

        for entry in entries:
            if entry.is_whitelisted:
                result["skipped"] += 1
                continue
            try:
                try:
                    self.add_to_whitelist(entry.wallet.address, wallet_uuid=entry.wallet_id)
                    result["added"] += 1
                except AddressAlreadyWhitelistedException:
                    self.sync_entry(entry.wallet.address, wallet_uuid=entry.wallet_id)
                    result["synced"] += 1
            except Exception as e:
                result["errors"].append(f"Failed to whitelist {entry.wallet.address}: {e}")
                logger.error(f"Failed to whitelist {entry.wallet.address}: {e}")

        return result

    def ensure_removed(self, entries: list[WhitelistEntry]) -> dict:
        result = {"removed": 0, "skipped": 0, "errors": []}

        for entry in entries:
            if not entry.is_whitelisted:
                result["skipped"] += 1
                continue
            try:
                try:
                    self.remove_from_whitelist(entry.wallet.address)
                except AddressNotWhitelistedException:
                    self.sync_entry(entry.wallet.address, wallet_uuid=entry.wallet_id)
                result["removed"] += 1
            except Exception as e:
                result["errors"].append(f"Failed to remove {entry.wallet.address}: {e}")
                logger.error(f"Failed to remove {entry.wallet.address}: {e}")

        return result
