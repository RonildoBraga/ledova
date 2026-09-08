import logging
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Optional

from django.conf import settings
from django.utils import timezone
from web3 import Web3

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain import BaseChainClient, get_base_chain_client
from shared.db import atomic
from wallets.models import Wallet
from whitelist.constants import (
    WHITELIST_STATUS_NOT_WHITELISTED,
    WHITELIST_STATUS_UNKNOWN,
    WHITELIST_STATUS_WHITELISTED,
)
from whitelist.exceptions import (
    AddressAlreadyWhitelistedException,
    AddressNotWhitelistedException,
    WalletNotRegisteredException,
    WhitelistContractNotConfiguredException,
    WhitelistOperationFailedException,
)
from whitelist.models import WhitelistEntry, WhitelistStatus

logger = logging.getLogger(__name__)

WHITELIST_ENTRY_LABEL = "whitelist.WhitelistEntry"


RECORD_A_REVERTED_WRITE = {
    TransactionType.WHITELIST_ADD: WhitelistEntry.mark_add_failed,
    TransactionType.WHITELIST_REMOVE: WhitelistEntry.mark_remove_failed,
}


def unique_wallet_uuid_for(address: str):
    wallet_ids = list(Wallet.objects.filter_by_address(address).order_by("uuid").values_list("uuid", flat=True)[:2])
    if len(wallet_ids) != 1:
        raise WalletNotRegisteredException()

    return wallet_ids[0]


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

    def can_receive(self, address: str) -> bool:
        checksum_address = self.chain_client.to_checksum_address(address)
        return self.contract.functions.canReceive(checksum_address).call()

    @staticmethod
    def _resolve_wallet(checksum_address: str, wallet_uuid=None) -> Wallet:
        wallets = Wallet.objects.filter_by_address(checksum_address).order_by("uuid")
        if wallet_uuid is not None:
            wallet = wallets.filter(uuid=wallet_uuid).first()
        else:
            matches = list(wallets[:2])
            wallet = matches[0] if len(matches) == 1 else None
        if wallet is None:
            raise WalletNotRegisteredException()
        return wallet

    @classmethod
    def _resolve_entry(cls, checksum_address: str, wallet_uuid=None) -> WhitelistEntry:
        if wallet_uuid is None:
            treasury = WhitelistEntry.objects.filter(wallet__isnull=True, address__iexact=checksum_address).first()
            if treasury is not None:
                return treasury
        wallet = cls._resolve_wallet(checksum_address, wallet_uuid)
        entry, _ = WhitelistEntry.objects.get_or_create(wallet=wallet, defaults={"status": WhitelistStatus.PENDING})
        return entry

    @staticmethod
    @atomic(durable=True)
    def _record_attempt(tx_type, function_name, checksum_address, signer_address, contract_address, entry):
        return BlockchainTransaction.objects.create(
            tx_type=tx_type,
            status=TransactionStatus.PENDING,
            from_address=signer_address,
            to_address=contract_address,
            function_name=function_name,
            function_args={"investor": checksum_address},
            related_model=WHITELIST_ENTRY_LABEL if entry else None,
            related_uuid=entry.uuid if entry else None,
        )

    @staticmethod
    @atomic(durable=True)
    def _record_sent(tx_record, entry, tx_hash) -> None:
        tx_record.mark_submitted(tx_hash)
        if entry and entry.status != WhitelistStatus.PENDING:
            entry.status = WhitelistStatus.PENDING
            entry.save(update_fields=["status", "updated_at"])

    def _refuse(self, tx_type, function_name, checksum_address, error):
        logger.error(f"{function_name}({checksum_address}) failed: {error}")
        return WhitelistOperationFailedException(f"{TransactionType(tx_type).label} failed.")

    def _send_tx(self, tx_type, function_name, checksum_address, entry, wait_for_receipt):
        tx_record = self._record_attempt(
            tx_type, function_name, checksum_address, self.signer_address, self.contract_address, entry
        )
        try:
            contract_function = getattr(self.contract.functions, function_name)(checksum_address)
            tx = self.chain_client.build_transaction(contract_function, from_address=self.signer_address)
            signed = self.chain_client.sign_transaction(tx, self.signer_key)
        except Exception as e:
            tx_record.mark_failed(str(e))
            if entry:
                entry.mark_failed(str(e))
            raise self._refuse(tx_type, function_name, checksum_address, e) from e

        try:
            tx_hash = self.chain_client.send_raw_transaction(signed)
        except Exception as e:
            tx_record.mark_outcome_unknown(str(e))
            raise self._refuse(tx_type, function_name, checksum_address, e) from e

        self._record_sent(tx_record, entry, tx_hash)
        logger.info(f"{function_name}({checksum_address}) sent (tx={tx_hash})")

        if not wait_for_receipt:
            return tx_hash, None

        try:
            receipt = self.chain_client.receipt_even_if_reverted(tx_hash)
        except Exception as e:
            tx_record.mark_outcome_unknown(str(e))
            raise self._refuse(tx_type, function_name, checksum_address, e) from e

        if receipt["status"] != 1:
            tx_record.mark_reverted(f"{function_name} reverted on chain ({tx_hash})")
            if entry:
                RECORD_A_REVERTED_WRITE[tx_type](entry, f"{function_name} reverted on chain", tx_hash)
            raise self._refuse(tx_type, function_name, checksum_address, f"reverted on chain ({tx_hash})")

        tx_record.mark_confirmed(
            block_number=receipt["blockNumber"],
            block_hash=Web3.to_hex(receipt["blockHash"]),
            gas_used=receipt["gasUsed"],
        )
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

        entry = self._resolve_entry(checksum_address, wallet_uuid)
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

    def investor_status(self, address: str) -> dict:
        try:
            info = self.get_investor_info(address)
            return {
                "address": self.chain_client.to_checksum_address(address),
                "is_whitelisted": info["whitelisted"],
                "can_receive": self.can_receive(address),
                "status": (WHITELIST_STATUS_WHITELISTED if info["whitelisted"] else WHITELIST_STATUS_NOT_WHITELISTED),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch whitelist status: {e}")
            return {
                "address": address,
                "is_whitelisted": False,
                "can_receive": False,
                "status": WHITELIST_STATUS_UNKNOWN,
            }

    def sync_entry(self, address: str, wallet_uuid=None) -> WhitelistEntry:
        checksum_address = self.chain_client.to_checksum_address(address)
        entry = self._resolve_entry(checksum_address, wallet_uuid)

        info = self.get_investor_info(checksum_address)
        kyc_ts = info["kyc_timestamp"]
        entry.is_whitelisted = info["whitelisted"]
        entry.on_chain_timestamp = datetime.fromtimestamp(kyc_ts, tz=dt_timezone.utc) if kyc_ts else None
        entry.status = WhitelistStatus.ACTIVE if info["whitelisted"] else WhitelistStatus.REMOVED
        entry.last_synced_at = timezone.now()
        entry.save(update_fields=["is_whitelisted", "on_chain_timestamp", "status", "last_synced_at", "updated_at"])

        logger.debug(f"Synced {checksum_address}: {info}")
        return entry

    def sync_entries(self, entries: list[WhitelistEntry]) -> dict:
        synced = 0
        errors = []

        for entry in entries:
            try:
                self.sync_entry(entry.wallet_address, wallet_uuid=entry.wallet_id)
                synced += 1
            except Exception as e:
                errors.append(f"Failed to sync {entry.wallet_address}: {e}")
                logger.error(f"Failed to sync {entry.wallet_address}: {e}")

        return {"synced": synced, "errors": errors}

    def sync_all_entries(self) -> int:
        entries = list(WhitelistEntry.objects.active() | WhitelistEntry.objects.pending())
        result = self.sync_entries(entries)
        logger.info(f"Synced {result['synced']} entries")
        return result["synced"]

    @staticmethod
    def _the_write_that_failed_was_an_add(entry) -> bool:
        latest = (
            BlockchainTransaction.objects.filter(related_model=WHITELIST_ENTRY_LABEL, related_uuid=entry.uuid)
            .order_by("-created_at")
            .values_list("tx_type", flat=True)
            .first()
        )
        return latest == TransactionType.WHITELIST_ADD

    def reconcile_failed_adds(self) -> dict:
        result = {"checked": 0, "activated": 0, "left_failed": 0, "removals_the_chain_kept": 0, "errors": []}

        for entry in WhitelistEntry.objects.failed_with_a_sent_add():
            result["checked"] += 1
            try:
                if not self.is_whitelisted(entry.wallet_address):
                    result["left_failed"] += 1
                    continue
            except Exception as exc:
                result["errors"].append(f"Could not read {entry.wallet_address}: {exc}")
                logger.error(f"Whitelist reconciliation could not read {entry.wallet_address}: {exc}")
                continue

            if not self._the_write_that_failed_was_an_add(entry):
                entry.record_the_chain_still_lists_it()
                result["removals_the_chain_kept"] += 1
                result["left_failed"] += 1
                logger.warning(
                    f"{entry.wallet_address} is still whitelisted on chain and the write that failed was a "
                    f"removal, so it stays failed for an operator to retry"
                )
                continue

            entry.mark_active(entry.add_tx_hash)
            result["activated"] += 1
            logger.warning(
                f"{entry.wallet_address} was recorded failed but the chain says it is whitelisted; "
                f"reconciled to active on {entry.add_tx_hash}"
            )

        return result

    def ensure_whitelisted(self, entries: list[WhitelistEntry]) -> dict:
        result = {"added": 0, "synced": 0, "skipped": 0, "errors": []}

        for entry in entries:
            if entry.is_whitelisted:
                result["skipped"] += 1
                continue
            try:
                try:
                    self.add_to_whitelist(entry.wallet_address, wallet_uuid=entry.wallet_id)
                    result["added"] += 1
                except AddressAlreadyWhitelistedException:
                    self.sync_entry(entry.wallet_address, wallet_uuid=entry.wallet_id)
                    result["synced"] += 1
            except Exception as e:
                result["errors"].append(f"Failed to whitelist {entry.wallet_address}: {e}")
                logger.error(f"Failed to whitelist {entry.wallet_address}: {e}")

        return result

    def ensure_removed(self, entries: list[WhitelistEntry]) -> dict:
        result = {"removed": 0, "skipped": 0, "errors": []}

        for entry in entries:
            if not entry.is_whitelisted:
                result["skipped"] += 1
                continue
            try:
                try:
                    self.remove_from_whitelist(entry.wallet_address)
                except AddressNotWhitelistedException:
                    self.sync_entry(entry.wallet_address, wallet_uuid=entry.wallet_id)
                result["removed"] += 1
            except Exception as e:
                result["errors"].append(f"Failed to remove {entry.wallet_address}: {e}")
                logger.error(f"Failed to remove {entry.wallet_address}: {e}")

        return result
