import csv
import io
from unittest.mock import Mock, patch

from web3 import Web3

from tokens.models import IssuanceStatus, ShareIssuance
from tokens.services.register import REGISTER_HEADERS
from tokens.services.share_token_service import ShareTokenService
from tokens.tests.test_register import RegisterTestBase, _account
from wallets.models import Wallet
from whitelist.models import WhitelistEntry, WhitelistStatus

ALLOTTEE = Web3.to_checksum_address("0x" + "a1" * 20)
TRANSFEREE = Web3.to_checksum_address("0x" + "e5" * 20)
ZERO_ADDRESS = "0x" + "0" * 40


class TransferAcquiredHolderTest(RegisterTestBase):

    def setUp(self):
        super().setUp()
        self.allottee = _account("allottee@example.test", "Alice Allottee")
        self.transferee = _account("transferee@example.test", "Tom Transferee")
        for account, address in ((self.allottee, ALLOTTEE), (self.transferee, TRANSFEREE)):
            wallet = Wallet.objects.create(user_account=account, address=address, chain="base")
            WhitelistEntry.objects.create(wallet=wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        ShareIssuance.objects.create(
            token=self.token,
            recipient_address=ALLOTTEE,
            amount="12000",
            status=IssuanceStatus.COMPLETED,
        )

    def _chain(self, balances, participants=(ALLOTTEE, TRANSFEREE), supply=12000):
        service = patch("tokens.services.register.ShareTokenService").start()
        self.addCleanup(patch.stopall)
        service.return_value.get_token_balance.side_effect = lambda contract, address: balances[address]
        service.return_value.transfer_participants.return_value = set(participants)
        service.return_value.share_supply.return_value = (12000, supply)
        return service

    def _holders(self):
        return self.client.get(f"/api/v1/tokens/{self.token.uuid}/holders/").json()

    def test_a_holder_who_acquired_by_transfer_is_in_the_register(self):
        self._chain({ALLOTTEE: 11000, TRANSFEREE: 1000})

        holders = self._holders()

        self.assertEqual({row["address"] for row in holders["holders"]}, {ALLOTTEE, TRANSFEREE})
        self.assertEqual(holders["totalHolders"], 2)

    def test_the_transferee_carries_their_chain_balance_and_their_name(self):
        self._chain({ALLOTTEE: 11000, TRANSFEREE: 1000})

        rows = {row["address"]: row for row in self._holders()["holders"]}

        self.assertEqual(rows[TRANSFEREE]["balance"], "1000")
        self.assertEqual(rows[TRANSFEREE]["name"], "Tom Transferee")

    def test_the_percentages_are_against_issued_supply_not_the_register_subtotal(self):
        self._chain({ALLOTTEE: 11000, TRANSFEREE: 1000})

        rows = {row["address"]: row for row in self._holders()["holders"]}

        self.assertEqual(rows[ALLOTTEE]["percentage"], 91.67)
        self.assertEqual(rows[TRANSFEREE]["percentage"], 8.33)

    def test_a_survivor_is_not_the_whole_register_when_supply_says_otherwise(self):
        self._chain({ALLOTTEE: 11000, TRANSFEREE: 0})

        holders = self._holders()
        rows = {row["address"]: row for row in holders["holders"]}

        self.assertEqual(list(rows), [ALLOTTEE])
        self.assertEqual(rows[ALLOTTEE]["percentage"], 91.67)
        self.assertEqual(holders["discrepancy"], "1000")

    def test_the_zero_address_is_not_a_holder(self):
        self._chain({ALLOTTEE: 12000}, participants=(ALLOTTEE, ZERO_ADDRESS))

        self.assertEqual({row["address"] for row in self._holders()["holders"]}, {ALLOTTEE})

    def test_the_export_says_what_it_could_not_account_for(self):
        self._chain({ALLOTTEE: 11000, TRANSFEREE: 0})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")
        rows = list(csv.reader(io.StringIO(response.content.decode())))

        self.assertEqual(
            rows[rows.index([]) + 1 : rows.index([]) + 4],
            [
                ["Issued supply", "12000"],
                ["Held by listed holders", "11000"],
                ["Not held by any listed holder", "1000"],
            ],
        )

    def test_the_export_prints_each_holders_share_of_issued_supply(self):
        self._chain({ALLOTTEE: 11000, TRANSFEREE: 1000})

        response = self.client.get(f"/api/v1/tokens/{self.token.uuid}/register/export/")
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        holders = {row[0]: dict(zip(REGISTER_HEADERS, row)) for row in rows[1 : rows.index([])]}

        self.assertEqual(holders["Alice Allottee"]["Percentage of issued supply"], "91.67%")
        self.assertEqual(holders["Tom Transferee"]["Percentage of issued supply"], "8.33%")

    def test_the_api_states_the_same_comparison_as_the_export(self):
        self._chain({ALLOTTEE: 11000, TRANSFEREE: 0})

        holders = self._holders()

        self.assertEqual(holders["issuedSupply"], "12000")
        self.assertEqual(holders["listedTotal"], "11000")
        self.assertEqual(holders["discrepancy"], "1000")


class TheTransferReadIsBoundedTest(RegisterTestBase):

    def test_the_log_read_is_chunked_and_never_asks_for_an_open_range(self):
        service = ShareTokenService.__new__(ShareTokenService)
        contract = Mock()
        contract.events.Transfer.return_value.get_logs.return_value = []

        with (
            patch.object(ShareTokenService, "load_share_token", return_value=contract),
            patch.object(ShareTokenService, "head_block", return_value=4500),
        ):
            service.transfer_participants("0x" + "c" * 40, from_block=1, window=2000)

        windows = [call.kwargs for call in contract.events.Transfer.return_value.get_logs.call_args_list]

        self.assertEqual(
            windows,
            [
                {"from_block": 1, "to_block": 2000},
                {"from_block": 2001, "to_block": 4000},
                {"from_block": 4001, "to_block": 4500},
            ],
        )

    def test_a_chunk_that_fails_is_a_failed_read_rather_than_a_short_answer(self):
        service = ShareTokenService.__new__(ShareTokenService)
        contract = Mock()
        contract.events.Transfer.return_value.get_logs.side_effect = RuntimeError("range too wide")

        with (
            patch.object(ShareTokenService, "load_share_token", return_value=contract),
            patch.object(ShareTokenService, "head_block", return_value=10),
            self.assertRaises(RuntimeError),
        ):
            service.transfer_participants("0x" + "c" * 40, from_block=1)
