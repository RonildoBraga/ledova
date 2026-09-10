from copy import deepcopy
from datetime import timedelta
from unittest import skipUnless

from django.conf import settings
from django.test import TransactionTestCase
from django.utils import timezone

from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from shared.utils.typed_data import build_domain, signable_message, typed_data_digest
from tokens.services.signing_challenge import CHALLENGE_TYPES
from tokens.tests.order_submission_fixtures import OWNER
from wallets.models import Wallet

_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Requires actual submission migrations")
class OrderSubmissionMigrationPreservesLegacyHistoryTest(TransactionTestCase):
    def test_unlinked_issued_and_spent_legacy_envelopes_survive_without_invented_submissions(self):
        tenant = make_tenant("submission-migration")
        wallet = Wallet.objects.create(user_account=tenant.account, address=OWNER.address, chain="base")
        before = migrate_to([("tokens", "0036_swap_expiry_eligibility")])
        self.addCleanup(restore_every_migration)
        challenges = before.get_model("tokens", "SigningChallenge").objects
        domain = build_domain(settings.BLOCKCHAIN_CHAIN_ID, tenant.deployed_token.contract_address)
        types = deepcopy(CHALLENGE_TYPES["order_create"])
        types["OrderCreate"] = [
            field
            for field in types["OrderCreate"]
            if field["name"] not in {"submissionId", "ownerAccountUuid", "walletUuid"}
        ]
        expires = timezone.now() + timedelta(minutes=5)
        originals = []
        for consumed in (False, True):
            nonce = 111 + int(consumed)
            message = {
                "tokenUuid": str(tenant.deployed_token.pk),
                "orderType": "buy",
                "quantity": "10",
                "minQuantity": "0",
                "pricePerShare": "2.50",
                "wallet": wallet.address,
                "nonce": str(nonce),
                "deadline": str(int(expires.timestamp())),
            }
            signature = OWNER.sign_message(signable_message(domain, types, message)).signature.to_0x_hex()
            challenge = challenges.create(
                purpose="order_create",
                wallet_id=wallet.pk,
                wallet_address=wallet.address,
                chain_id=domain["chainId"],
                verifying_contract=domain["verifyingContract"],
                payload={"domain": domain, "types": types, "message": message},
                digest=typed_data_digest(domain, types, message),
                nonce=nonce,
                expires_at=expires,
                consumed_at=timezone.now() if consumed else None,
                consumed_signature=signature if consumed else "",
            )
            originals.append(challenges.filter(pk=challenge.pk).values().get())

        after = migrate_to([("tokens", "0037_order_submissions")])

        for original in originals:
            current = after.get_model("tokens", "SigningChallenge").objects.filter(pk=original["uuid"]).values().get()
            self.assertIsNone(current.pop("submission_id"))
            self.assertEqual(current, original)
        self.assertEqual(after.get_model("tokens", "OrderSubmission").objects.count(), 0)
