from unittest.mock import Mock

from django.db import transaction
from django.test import TestCase, TransactionTestCase

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain.exceptions import BaseChainTransactionError
from users.models import UserAccount
from wallets.models import Wallet
from whitelist.exceptions import (
    AddressAlreadyWhitelistedException,
    AddressNotWhitelistedException,
    WalletNotRegisteredException,
    WhitelistOperationFailedException,
)
from whitelist.models import WhitelistEntry, WhitelistStatus
from whitelist.services import WhitelistService

RECEIPT = {"status": 1, "blockNumber": 7, "blockHash": bytes.fromhex("ab" * 32), "gasUsed": 21000}
SIGNER = "0x" + "f" * 40
ADD_HASH = "0x" + "11" * 32
REMOVE_HASH = "0x" + "22" * 32


class WhitelistServiceTransactionTest(TransactionTestCase):
    def setUp(self):
        self.account = UserAccount.objects.create()
        self.wallet = Wallet.objects.create(user_account=self.account, address="0x" + "a" * 40, chain="base")
        self.entry = WhitelistEntry.objects.create(wallet=self.wallet)

    def _service(self, on_chain=False):
        service = WhitelistService.__new__(WhitelistService)
        service.chain_client = Mock()
        service.chain_client.to_checksum_address.side_effect = lambda address: address
        service.chain_client.account_from_key.return_value.address = SIGNER
        service.chain_client.build_transaction.return_value = {}
        service.chain_client.sign_transaction.return_value = b"signed"
        service.chain_client.send_raw_transaction.return_value = "0xhash"
        service.chain_client.receipt_even_if_reverted.return_value = RECEIPT
        service.signer_key = "0xoperator"
        service.contract_address = "0x" + "d" * 40
        service._contract = Mock()
        service.is_whitelisted = Mock(return_value=on_chain)
        return service

    def test_add_records_a_confirmed_transaction_and_activates_the_entry(self):
        service = self._service()

        tx_hash, entry = service.add_to_whitelist(self.wallet.address)

        self.assertEqual(tx_hash, "0xhash")
        self.assertEqual(entry, self.entry)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, WhitelistStatus.ACTIVE)
        self.assertTrue(self.entry.is_whitelisted)
        self.assertEqual(self.entry.add_tx_hash, "0xhash")
        record = BlockchainTransaction.objects.get()
        self.assertEqual(record.tx_type, TransactionType.WHITELIST_ADD)
        self.assertEqual(record.status, TransactionStatus.CONFIRMED)
        self.assertEqual(record.function_name, "addToWhitelist")
        self.assertEqual(record.function_args, {"investor": self.wallet.address})
        self.assertEqual((record.from_address, record.to_address), (SIGNER, service.contract_address))
        self.assertEqual((record.related_model, record.related_uuid), ("whitelist.WhitelistEntry", self.entry.uuid))
        self.assertEqual((record.tx_hash, record.block_number, record.gas_used), ("0xhash", 7, 21000))
        service._contract.functions.addToWhitelist.assert_called_once_with(self.wallet.address)
        service.chain_client.build_transaction.assert_called_once_with(
            service._contract.functions.addToWhitelist.return_value, from_address=SIGNER
        )

    def test_add_creates_the_entry_for_a_wallet_without_one(self):
        wallet = Wallet.objects.create(user_account=self.account, address="0x" + "b" * 40, chain="base")

        _, entry = self._service().add_to_whitelist(wallet.address)

        self.assertEqual(entry.wallet, wallet)
        self.assertEqual(entry.status, WhitelistStatus.ACTIVE)

    def test_add_uses_the_given_wallet_when_the_address_is_duplicated(self):
        Wallet.objects.create(user_account=UserAccount.objects.create(), address=self.wallet.address, chain="ethereum")

        _, entry = self._service().add_to_whitelist(self.wallet.address, wallet_uuid=self.wallet.uuid)

        self.assertEqual(entry, self.entry)

    def test_add_refuses_an_address_already_on_chain_before_writing(self):
        with self.assertRaises(AddressAlreadyWhitelistedException):
            self._service(on_chain=True).add_to_whitelist(self.wallet.address)

        self.assertFalse(BlockchainTransaction.objects.exists())

    def test_a_refusal_before_the_send_is_failed_and_says_why(self):
        service = self._service()
        service.chain_client.sign_transaction.side_effect = BaseChainTransactionError("boom")

        with self.assertRaises(WhitelistOperationFailedException) as ctx:
            service.add_to_whitelist(self.wallet.address)

        self.assertEqual(str(ctx.exception.detail), "Add to Whitelist failed.")
        record = BlockchainTransaction.objects.get()
        self.assertEqual(
            (record.status, record.error_message, record.tx_hash), (TransactionStatus.FAILED, "boom", None)
        )
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, WhitelistStatus.FAILED)
        self.assertIn("Error: boom", self.entry.notes)

    def test_a_send_whose_fate_is_unknown_is_not_called_failed(self):
        for operation, on_chain, status in (
            ("add_to_whitelist", False, WhitelistStatus.PENDING),
            ("add_to_whitelist", False, WhitelistStatus.FAILED),
            ("add_to_whitelist", False, WhitelistStatus.REMOVED),
            ("remove_from_whitelist", True, WhitelistStatus.ACTIVE),
            ("remove_from_whitelist", True, WhitelistStatus.FAILED),
        ):
            with self.subTest(operation=operation, status=status):
                BlockchainTransaction.objects.all().delete()
                WhitelistEntry.objects.filter(pk=self.entry.pk).update(status=status, is_whitelisted=on_chain)
                service = self._service(on_chain=on_chain)
                service.chain_client.send_raw_transaction.side_effect = BaseChainTransactionError("no response")

                with self.assertRaises(WhitelistOperationFailedException):
                    getattr(service, operation)(self.wallet.address)

                record = BlockchainTransaction.objects.get()
                self.assertEqual((record.status, record.tx_hash), (TransactionStatus.PENDING, None))
                self.assertIn("no response", record.error_message)
                self.entry.refresh_from_db()
                self.assertEqual(self.entry.status, WhitelistStatus.PENDING)
                self.assertEqual(self.entry.is_whitelisted, on_chain)

    def test_a_receipt_that_never_arrives_keeps_the_hash_and_leaves_the_entry_pending(self):
        service = self._service()
        service.chain_client.receipt_even_if_reverted.side_effect = BaseChainTransactionError("receipt timed out")

        with self.assertRaises(WhitelistOperationFailedException):
            service.add_to_whitelist(self.wallet.address)

        record = BlockchainTransaction.objects.get()
        self.assertEqual((record.status, record.tx_hash), (TransactionStatus.SUBMITTED, "0xhash"))
        self.assertIn("receipt timed out", record.error_message)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, WhitelistStatus.PENDING)

    def test_an_add_the_chain_reverted_keeps_its_hash_on_the_entry(self):
        service = self._service()
        service.chain_client.receipt_even_if_reverted.return_value = {**RECEIPT, "status": 0}

        with self.assertRaises(WhitelistOperationFailedException):
            service.add_to_whitelist(self.wallet.address)

        record = BlockchainTransaction.objects.get()
        self.assertEqual((record.status, record.tx_hash), (TransactionStatus.REVERTED, "0xhash"))
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.status, self.entry.add_tx_hash), (WhitelistStatus.FAILED, "0xhash"))

    def test_a_reverted_remove_records_its_own_hash_and_leaves_the_add_hash_alone(self):
        service = self._service(on_chain=True)
        WhitelistEntry.objects.filter(pk=self.entry.pk).update(
            status=WhitelistStatus.ACTIVE, is_whitelisted=True, add_tx_hash=ADD_HASH
        )
        service.chain_client.send_raw_transaction.return_value = REMOVE_HASH
        service.chain_client.receipt_even_if_reverted.return_value = {**RECEIPT, "status": 0}

        with self.assertRaises(WhitelistOperationFailedException):
            service.remove_from_whitelist(self.wallet.address)

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, WhitelistStatus.FAILED)
        self.assertEqual(self.entry.add_tx_hash, ADD_HASH)
        self.assertEqual(self.entry.remove_tx_hash, REMOVE_HASH)

    def test_a_removal_can_be_retried_on_an_entry_the_sweeper_left_failed(self):
        service = self._service(on_chain=True)
        WhitelistEntry.objects.filter(pk=self.entry.pk).update(
            status=WhitelistStatus.FAILED, is_whitelisted=True, add_tx_hash=ADD_HASH, remove_tx_hash=REMOVE_HASH
        )
        service.chain_client.send_raw_transaction.return_value = "0xsecondtry"

        tx_hash, entry = service.remove_from_whitelist(self.wallet.address)

        self.assertEqual(tx_hash, "0xsecondtry")
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, WhitelistStatus.REMOVED)
        self.assertEqual((self.entry.add_tx_hash, self.entry.remove_tx_hash), (ADD_HASH, "0xsecondtry"))

    def test_a_caller_that_wraps_the_add_in_a_transaction_is_refused(self):
        service = self._service()

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                service.add_to_whitelist(self.wallet.address)

        service.chain_client.send_raw_transaction.assert_not_called()
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, WhitelistStatus.PENDING)

    def test_remove_marks_the_entry_removed(self):
        self.entry.mark_active("0xearlier")
        service = self._service(on_chain=True)

        tx_hash, entry = service.remove_from_whitelist(self.wallet.address)

        self.assertEqual((tx_hash, entry), ("0xhash", self.entry))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, WhitelistStatus.REMOVED)
        self.assertFalse(self.entry.is_whitelisted)
        self.assertEqual(self.entry.remove_tx_hash, "0xhash")
        record = BlockchainTransaction.objects.get()
        self.assertEqual(
            (record.tx_type, record.status), (TransactionType.WHITELIST_REMOVE, TransactionStatus.CONFIRMED)
        )
        service._contract.functions.removeFromWhitelist.assert_called_once_with(self.wallet.address)

    def test_remove_without_a_database_entry_still_records_the_transaction(self):
        unknown = "0x" + "e" * 40

        tx_hash, entry = self._service(on_chain=True).remove_from_whitelist(unknown)

        self.assertEqual((tx_hash, entry), ("0xhash", None))
        record = BlockchainTransaction.objects.get()
        self.assertEqual((record.related_model, record.related_uuid), (None, None))

    def test_remove_refuses_an_address_not_on_chain(self):
        with self.assertRaises(AddressNotWhitelistedException):
            self._service().remove_from_whitelist(self.wallet.address)

        self.assertFalse(BlockchainTransaction.objects.exists())

    def test_sync_resolves_the_wallet_like_add_does(self):
        service = self._service()
        service.get_investor_info = Mock(return_value={"whitelisted": True, "kyc_timestamp": 0})

        with self.assertRaises(WalletNotRegisteredException):
            service.sync_entry("0x" + "9" * 40)

        entry = service.sync_entry(self.wallet.address)
        self.assertEqual((entry, entry.status), (self.entry, WhitelistStatus.ACTIVE))

    def test_batch_add_is_gone(self):
        self.assertFalse(hasattr(WhitelistService, "batch_add_to_whitelist"))


class WhitelistServiceEnsureTest(TestCase):
    def setUp(self):
        account = UserAccount.objects.create()
        self.entries = {}
        for label in ("new", "onchain", "active", "broken"):
            wallet = Wallet.objects.create(user_account=account, address="0x" + label.ljust(40, "0"), chain="base")
            self.entries[label] = WhitelistEntry.objects.create(wallet=wallet)
        self.entries["active"].is_whitelisted = True
        self.entries["active"].save(update_fields=["is_whitelisted"])

    def _service(self):
        service = WhitelistService.__new__(WhitelistService)
        outcomes = {
            self.entries["onchain"].wallet.address: AddressAlreadyWhitelistedException(),
            self.entries["broken"].wallet.address: RuntimeError("rpc down"),
        }

        def add(address, wait_for_receipt=True, wallet_uuid=None):
            if address in outcomes:
                raise outcomes[address]
            return "0xhash", None

        service.add_to_whitelist = Mock(side_effect=add)
        service.sync_entry = Mock()
        service.remove_from_whitelist = Mock()
        return service

    def test_ensure_whitelisted_adds_syncs_skips_and_reports(self):
        service = self._service()

        result = service.ensure_whitelisted(list(self.entries.values()))

        self.assertEqual((result["added"], result["synced"], result["skipped"]), (1, 1, 1))
        self.assertEqual(result["errors"], [f"Failed to whitelist {self.entries['broken'].wallet.address}: rpc down"])
        new = self.entries["new"]
        service.add_to_whitelist.assert_any_call(new.wallet.address, wallet_uuid=new.wallet_id)
        onchain = self.entries["onchain"]
        service.sync_entry.assert_called_once_with(onchain.wallet.address, wallet_uuid=onchain.wallet_id)

    def test_ensure_whitelisted_reports_a_failed_sync_instead_of_raising(self):
        service = self._service()
        service.sync_entry.side_effect = RuntimeError("sync down")

        result = service.ensure_whitelisted([self.entries["onchain"]])

        self.assertEqual((result["added"], result["synced"]), (0, 0))
        self.assertEqual(len(result["errors"]), 1)

    def test_ensure_removed_syncs_when_already_gone_and_reports_failures(self):
        service = self._service()
        active, new = self.entries["active"], self.entries["new"]
        service.remove_from_whitelist.side_effect = AddressNotWhitelistedException()

        result = service.ensure_removed([active, new])
        self.assertEqual(result, {"removed": 1, "skipped": 1, "errors": []})
        service.sync_entry.assert_called_once_with(active.wallet.address, wallet_uuid=active.wallet_id)

        service.sync_entry.side_effect = RuntimeError("sync down")
        result = service.ensure_removed([active])
        self.assertEqual((result["removed"], len(result["errors"])), (0, 1))
