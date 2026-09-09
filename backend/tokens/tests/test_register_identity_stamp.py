import csv
import io
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from web3 import Web3

from shared.tests.tenants import make_tenant
from tokens.models import RequestStatus, ShareIssuance, ShareIssuanceRequest
from tokens.services import ShareTokenService
from tokens.services.holder_identity import identity_at_allotment
from tokens.services.register import (
    IDENTITY_BY_HOLDER_TYPE,
    IDENTITY_LABELS,
    IDENTITY_LIVE,
    IDENTITY_NONE,
    IDENTITY_RECORDED,
    REGISTER_HEADERS,
    export_rows,
    token_register,
)
from users.models import UserAccount
from wallets.models import Wallet
from whitelist.models import HolderType, WhitelistEntry

HOLDER = "0x" + "ab" * 20
CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"
WHITELISTED = "tokens.services.share_token_service.ShareTokenService.is_recipient_whitelisted"
SUPPLY = "tokens.services.share_token_service.ShareTokenService.share_supply"
IDENTITY_COLUMN = REGISTER_HEADERS.index("Identity source")


class EveryHolderTypeStatesItsOwnIdentitySourceTest(TestCase):
    def test_no_holder_type_can_exist_without_an_identity_source(self):
        self.assertEqual(set(HolderType.values) - set(IDENTITY_BY_HOLDER_TYPE), set())

    def test_every_mapped_source_has_a_label(self):
        self.assertEqual(set(IDENTITY_BY_HOLDER_TYPE.values()) - set(IDENTITY_LABELS), set())

    def test_only_a_member_may_claim_a_current_profile(self):
        claiming_live = [
            holder_type for holder_type, source in IDENTITY_BY_HOLDER_TYPE.items() if source == IDENTITY_LIVE
        ]

        self.assertEqual(claiming_live, [HolderType.MEMBER.value])


class IdentitySurvivesAWalletDeletionTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("stamp")
        self.token = self.tenant.deployed_token
        profile = self.tenant.profile
        profile.full_name = "Ada Lovelace"
        profile.residential_address = "1 Analytical Way"
        profile.save(update_fields=["full_name", "residential_address"])
        self.account = UserAccount.objects.create()
        self.account.user_profiles.add(profile)
        self.wallet = Wallet.objects.create(user_account=self.account, address=HOLDER, chain="base")
        WhitelistEntry.objects.create(wallet=self.wallet)
        self.chain = Mock()
        self.chain.deployment_block.return_value = 1
        self.chain.transfer_participants.return_value = set()
        self.chain.get_token_balance.return_value = 100
        self.chain.share_supply.return_value = (1000, 100)
        service = patch("tokens.services.register.ShareTokenService").start()
        service.return_value = self.chain
        self.addCleanup(patch.stopall)

    def _allot(self, name="", address="", stamped=True):
        return ShareIssuance.objects.create(
            token=self.token,
            recipient_address=HOLDER,
            recipient_name=name,
            recipient_residential_address=address,
            identity_stamped_at=timezone.now() if stamped else None,
            amount="100",
            status="completed",
        )

    def _row(self):
        rows, _ = token_register(self.token, service=self.chain)
        return next(row for row in rows if row["address"].lower() == HOLDER)

    def test_the_stamp_resolves_the_holders_identity_at_allotment(self):
        stamped = identity_at_allotment(HOLDER, chain="base")

        self.assertEqual((stamped.name, stamped.residential_address), ("Ada Lovelace", "1 Analytical Way"))

    def test_an_unknown_address_stamps_nothing(self):
        stamped = identity_at_allotment("0x" + "cd" * 20, chain="base")

        self.assertFalse(stamped)

    def test_live_identity_is_used_while_the_wallet_stands(self):
        self._allot(name="Ada Lovelace", address="1 Analytical Way")

        row = self._row()

        self.assertEqual(row["name"], "Ada Lovelace")
        self.assertEqual(row["residential_address"], "1 Analytical Way")
        self.assertEqual(row["holder_type"], "member")
        self.assertEqual(row["identity_source"], IDENTITY_LABELS[IDENTITY_LIVE])

    def test_the_stamp_carries_the_member_through_a_wallet_deletion(self):
        self._allot(name="Ada Lovelace", address="1 Analytical Way")

        self.wallet.delete()
        row = self._row()

        self.assertEqual(row["name"], "Ada Lovelace")
        self.assertEqual(row["residential_address"], "1 Analytical Way")
        self.assertEqual(row["holder_type"], "member")
        self.assertTrue(row["identity_source"].startswith("Stamped at allotment on "))

    def test_a_moved_member_keeps_the_current_address_not_the_stamped_one(self):
        self._allot(name="Ada Lovelace", address="1 Analytical Way")
        profile = self.tenant.profile
        profile.residential_address = "2 Difference Engine Lane"
        profile.save(update_fields=["residential_address"])

        row = self._row()

        self.assertEqual(row["residential_address"], "2 Difference Engine Lane")
        self.assertEqual(row["identity_source"], IDENTITY_LABELS[IDENTITY_LIVE])

    def test_an_operator_label_names_the_holder_without_claiming_to_identify_them(self):
        self._allot(name="Stranger from a spreadsheet", stamped=False)
        self.wallet.delete()

        row = self._row()

        self.assertEqual(row["name"], "Stranger from a spreadsheet")
        self.assertEqual(row["residential_address"], "")
        self.assertEqual(row["holder_type"], "unidentified")
        self.assertEqual(row["identity_source"], IDENTITY_LABELS[IDENTITY_RECORDED])

    def test_a_holder_with_nothing_recorded_is_not_identified(self):
        self._allot(stamped=False)
        self.wallet.delete()

        row = self._row()

        self.assertIsNone(row["name"])
        self.assertEqual(row["holder_type"], "unidentified")
        self.assertEqual(row["identity_source"], IDENTITY_LABELS[IDENTITY_NONE])

    def test_the_export_says_which_identity_it_used(self):
        self._allot(name="Ada Lovelace", address="1 Analytical Way")
        self.wallet.delete()

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(REGISTER_HEADERS)
        for row in export_rows(self.token, None):
            writer.writerow(row)
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))

        self.assertEqual(rows[0], REGISTER_HEADERS)
        self.assertTrue(rows[1][IDENTITY_COLUMN].startswith("Stamped at allotment on "), rows[1])
        self.assertEqual(rows[1][0], "Ada Lovelace")
        self.assertEqual(rows[1][1], "1 Analytical Way")


class TheIssuancePathStampsWhatItAllotsTest(TestCase):
    def setUp(self):
        self.chain = patch(CHAIN_CLIENT).start().return_value
        self.chain.is_valid_address.return_value = True
        self.chain.to_checksum_address.side_effect = Web3.to_checksum_address
        self.chain.load_contract.return_value.functions.paused.return_value.call.return_value = False
        patch(WHITELISTED, return_value=True).start()
        patch(SUPPLY, return_value=(1000, 0)).start()
        self.addCleanup(patch.stopall)

        self.tenant = make_tenant("issuance-stamp")
        self.token = self.tenant.deployed_token
        profile = self.tenant.profile
        profile.full_name = "Grace Hopper"
        profile.residential_address = "3 Compiler Court"
        profile.save(update_fields=["full_name", "residential_address"])
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        Wallet.objects.create(user_account=account, address=HOLDER, chain="base")

        self.service = ShareTokenService()

    def _execute(self, recipient=HOLDER, label=""):
        request = ShareIssuanceRequest.objects.create(
            token=self.token,
            recipient_address=recipient,
            recipient_name=label,
            amount=5,
            submitted_by=self.tenant.user,
        )
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        request.refresh_from_db()
        try:
            self.service.execute_request(request)
        except Exception:
            pass
        return ShareIssuance.objects.filter(token=self.token).order_by("-created_at").first()

    def test_the_row_is_stamped_before_the_chain_is_asked_to_mint(self):
        issuance = self._execute()

        self.assertIsNotNone(issuance)
        self.assertEqual(issuance.recipient_address.lower(), HOLDER)

    def test_the_issuance_records_who_the_holder_was_when_the_shares_were_allotted(self):
        issuance = self._execute()

        self.assertEqual(issuance.recipient_name, "Grace Hopper")
        self.assertEqual(issuance.recipient_residential_address, "3 Compiler Court")
        self.assertIsNotNone(issuance.identity_stamped_at)

    def test_a_resolved_profile_beats_an_operators_label_for_the_name_it_stamps(self):
        issuance = self._execute(label="Payroll wallet")

        self.assertEqual(issuance.recipient_name, "Grace Hopper")
        self.assertEqual(issuance.recipient_residential_address, "3 Compiler Court")
        self.assertIsNotNone(issuance.identity_stamped_at)

    def test_a_label_on_an_address_nobody_resolved_stamps_nothing(self):
        issuance = self._execute(recipient="0x" + "cd" * 20, label="Payroll wallet")

        self.assertEqual(issuance.recipient_name, "Payroll wallet")
        self.assertEqual(issuance.recipient_residential_address, "")
        self.assertIsNone(issuance.identity_stamped_at)

    def test_an_address_belonging_to_nobody_is_recorded_as_unstamped(self):
        issuance = self._execute(recipient="0x" + "cd" * 20)

        self.assertEqual(issuance.recipient_name, "")
        self.assertEqual(issuance.recipient_residential_address, "")
        self.assertIsNone(issuance.identity_stamped_at)
