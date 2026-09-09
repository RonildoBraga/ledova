from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from eth_account import Account
from eth_account.messages import encode_defunct
from rest_framework.test import APITestCase

from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from wallets.models import Wallet


class SigningPreferenceTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("signing-pref")
        self.client.force_authenticate(self.tenant.user)

    def create(self, **preference):
        return self.client.post(
            "/api/wallets/",
            {
                "userAccount": str(self.tenant.account.pk),
                "address": Account.create().address,
                "chain": "base",
                **preference,
            },
            format="json",
        )

    def test_an_omitted_preference_does_not_claim_hardware(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.json()["signingPreference"])
        self.assertIsNone(response.json()["walletType"])
        self.assertEqual(response.json()["verificationStatus"], "PENDING")

    def test_the_preference_is_self_declared_through_either_api_name(self):
        for name in ("signingPreference", "walletType"):
            for preference in ("hardware", "software"):
                with self.subTest(name=name, preference=preference):
                    response = self.create(**{name: preference})
                    self.assertEqual(response.status_code, 201, response.content)
                    self.assertEqual(response.json()["signingPreference"], preference)
                    self.assertEqual(response.json()["walletType"], preference)
                    self.assertEqual(response.json()["verificationStatus"], "PENDING")

    def test_conflicting_legacy_and_current_names_are_refused(self):
        response = self.create(signingPreference="hardware", walletType="software")
        self.assertEqual(response.status_code, 400)
        self.assertIn("signingPreference", response.json())

    def test_empty_preferences_are_rejected_and_null_clears_either_alias(self):
        for name in ("signingPreference", "walletType"):
            with self.subTest(name=name):
                refused = self.create(**{name: ""})
                self.assertEqual(refused.status_code, 400, refused.content)
                created = self.create(**{name: "hardware"})
                self.assertEqual(created.status_code, 201, created.content)
                url = f"/api/wallets/{created.json()['uuid']}/"
                self.assertEqual(self.client.patch(url, {name: ""}, format="json").status_code, 400)
                cleared = self.client.patch(url, {name: None}, format="json")
                self.assertEqual(cleared.status_code, 200, cleared.content)
                self.assertIsNone(cleared.json()["signingPreference"])
                self.assertIsNone(cleared.json()["walletType"])

    def test_import_metadata_does_not_attest_hardware_or_select_a_preference(self):
        response = self.create(masterFingerprint="a1b2c3d4", parentPublicKey="02" + "1" * 64)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.json()["signingPreference"])
        self.assertEqual(response.json()["verificationStatus"], "PENDING")

    @patch("wallets.tasks.sync_wallet.defer")
    def test_a_signature_from_code_proves_address_control_for_either_preference(self, defer):
        for preference in ("hardware", "software"):
            with self.subTest(preference=preference):
                signer = Account.create()
                wallet = Wallet.objects.create(
                    user_account=self.tenant.account,
                    address=signer.address,
                    chain="base",
                    signing_preference=preference,
                )
                issued = self.client.post(f"/api/wallets/{wallet.pk}/request-verification/")
                self.assertEqual(issued.status_code, 200)
                signature = signer.sign_message(encode_defunct(text=issued.json()["challenge"])).signature.to_0x_hex()
                verified = self.client.post(
                    f"/api/wallets/{wallet.pk}/verify-signature/", {"signature": signature}, format="json"
                )
                self.assertEqual(verified.status_code, 200, verified.content)
                changed = self.client.patch(
                    f"/api/wallets/{wallet.pk}/",
                    {"signingPreference": "software" if preference == "hardware" else "hardware"},
                    format="json",
                )
                self.assertEqual(changed.status_code, 200, changed.content)
                wallet.refresh_from_db()
                self.assertEqual(wallet.verification_status, "VERIFIED")
                self.assertEqual(wallet.verification_signature, signature)
        self.assertEqual(defer.call_count, 2)

    def test_a_preference_does_not_give_another_account_access_to_the_wallet(self):
        other = make_tenant("other-pref")
        response = self.client.patch(
            f"/api/wallets/{other.wallet.pk}/", {"signingPreference": "hardware"}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        other.wallet.refresh_from_db()
        self.assertIsNone(other.wallet.signing_preference)


modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class SigningPreferenceMigrationTest(TransactionTestCase):
    def test_renaming_preserves_both_recorded_preferences_and_wallet_identity(self):
        tenant = make_tenant("pref-migration")
        self.addCleanup(restore_every_migration)
        historical = migrate_to([("wallets", "0012_balance_versions")]).get_model("wallets", "Wallet")
        ids = []
        for preference in ("hardware", "software"):
            row = historical.objects.create(
                user_account_id=tenant.account.pk,
                address=Account.create().address,
                chain="base",
                wallet_type=preference,
            )
            ids.append((row.pk, row.address, preference))
        restore_every_migration()
        for uuid, address, preference in ids:
            current = Wallet.objects.get(pk=uuid)
            self.assertEqual((current.address, current.signing_preference), (address, preference))
