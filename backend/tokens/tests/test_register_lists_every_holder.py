from unittest.mock import patch

from web3 import Web3

from tokens.models import IssuanceStatus, ShareIssuance
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
