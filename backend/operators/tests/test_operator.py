from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment
from operators.models import SINGLETON_PK, DeploymentMode, Operator, ReceivingChain
from operators.serializers import OperatorSerializer

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
WALLET = "0x" + "ab" * 20
PUBLIC_KEYS = {
    "name",
    "legal_name",
    "abn",
    "contact_email",
    "website",
    "deployment_mode",
    "supported_settlement_assets",
    "issued_stablecoin",
    "investor_kyc_required",
    "issuer_kyc_required",
    "payment_instructions",
}
PUBLIC_JSON_KEYS = {
    "name",
    "legalName",
    "abn",
    "contactEmail",
    "website",
    "deploymentMode",
    "supportedSettlementAssets",
    "issuedStablecoin",
    "investorKycRequired",
    "issuerKycRequired",
    "paymentInstructions",
}


def stablecoin(symbol="AUDY", chain="base"):
    asset = Asset.objects.create(symbol=symbol, name=f"{symbol} dollar", asset_type="stablecoin", decimals=6)
    AssetChainDeployment.objects.create(asset=asset, chain=chain, contract_address="0x" + "5" * 40, decimals=6)
    return asset


class OperatorModelTest(TestCase):
    @override_settings(OPERATOR_NAME="Acme Registry")
    def test_get_seeds_one_row_from_settings_and_returns_it_afterwards(self):
        self.assertFalse(Operator.objects.exists())

        operator = Operator.get()

        self.assertEqual((operator.pk, operator.name), (SINGLETON_PK, "Acme Registry"))
        self.assertEqual((operator.deployment_mode, operator.receiving_wallet_chain), ("registry", "base"))
        self.assertEqual((operator.investor_kyc_required, operator.issuer_kyc_required), (True, False))
        operator.name = "Renamed"
        operator.save(update_fields=["name"])
        self.assertEqual(Operator.get().name, "Renamed")
        self.assertEqual(Operator.objects.count(), 1)

    def test_a_second_row_is_refused_by_save_and_by_the_database(self):
        Operator.get()

        with self.assertRaisesMessage(ValidationError, "Only one operator row can exist"):
            Operator(name="Second").save()
        self.assertEqual(Operator.objects.count(), 1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Operator.objects.bulk_create([Operator(id=2, name="Third")])
        self.assertEqual(Operator.objects.count(), 1)

    def test_clean_normalises_and_validates_the_bank_and_wallet_fields(self):
        operator = Operator.get()
        operator.abn = "51 824 753 556"
        operator.bank_bsb = "062-000"
        operator.payment_reference_prefix = "ldv"
        operator.receiving_wallet_address = WALLET
        operator.clean()
        self.assertEqual(
            (operator.abn, operator.bank_bsb, operator.payment_reference_prefix), ("51824753556", "062000", "LDV")
        )
        self.assertEqual(operator.receiving_wallet_address, "0xABaBaBaBABabABabAbAbABAbABabababaBaBABaB")

        bad = Operator.get()
        bad.abn = "123"
        bad.bank_bsb = "12345"
        bad.payment_reference_prefix = "with space"
        bad.receiving_wallet_address = "0x1234"
        bad.issued_stablecoin = Asset.objects.create(symbol="NOTSTABLE", name="Not", asset_type="erc20_token")
        with self.assertRaises(ValidationError) as ctx:
            bad.clean()
        self.assertEqual(
            set(ctx.exception.message_dict),
            {"abn", "bank_bsb", "payment_reference_prefix", "receiving_wallet_address", "issued_stablecoin"},
        )


@override_settings(STORAGES=TEST_STORAGES)
class OperatorAdminTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(email="admin@example.test", password="pw-12345678"))
        self.changelist_url = reverse("admin:operators_operator_changelist")
        self.add_url = reverse("admin:operators_operator_add")

    def test_changelist_seeds_the_row_and_lands_on_its_change_page(self):
        response = self.client.get(self.changelist_url)

        change_url = reverse("admin:operators_operator_change", args=[SINGLETON_PK])
        self.assertRedirects(response, change_url, fetch_redirect_response=False)
        self.assertEqual(Operator.objects.count(), 1)
        page = self.client.get(change_url)
        self.assertEqual(page.status_code, 200)
        for legend in ("Identity", "Deployment", "Payments", "Eligibility"):
            self.assertContains(page, legend)

    def test_add_is_offered_only_while_no_row_exists_and_delete_never(self):
        self.assertEqual(self.client.get(self.add_url).status_code, 200)
        Operator.get()
        self.assertEqual(self.client.get(self.add_url).status_code, 403)
        delete_url = reverse("admin:operators_operator_delete", args=[SINGLETON_PK])
        self.assertEqual(self.client.get(delete_url).status_code, 403)
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 403)
        self.assertEqual(Operator.objects.count(), 1)

    def test_change_form_validates_and_limits_the_asset_choices_to_stablecoins(self):
        audy = stablecoin()
        other = Asset.objects.create(symbol="LINK", name="Chainlink", asset_type="erc20_token")
        operator = Operator.get()
        change_url = reverse("admin:operators_operator_change", args=[operator.pk])
        page = self.client.get(change_url)
        self.assertContains(page, "AUDY")
        self.assertNotContains(page, "LINK - Chainlink")

        payload = {
            "name": "Acme",
            "contact_email": "ops@acme.test",
            "deployment_mode": DeploymentMode.SINGLE_ISSUER,
            "bank_bsb": "12345",
            "receiving_wallet_chain": ReceivingChain.BASE,
            "supported_settlement_assets": [str(other.pk)],
            "investor_kyc_required": "on",
        }
        response = self.client.post(change_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BSB must be exactly 6 digits.")
        self.assertContains(response, "Select a valid choice.")

        payload.update(bank_bsb="062-000", bank_account_number="12345678", bank_account_name="Acme Pty Ltd")
        payload["supported_settlement_assets"] = [str(audy.pk)]
        payload["issued_stablecoin"] = str(audy.pk)
        response = self.client.post(change_url, payload)
        self.assertRedirects(response, self.changelist_url, fetch_redirect_response=False)
        operator.refresh_from_db()
        self.assertEqual((operator.bank_bsb, operator.deployment_mode), ("062000", "single_issuer"))
        self.assertEqual(list(operator.supported_settlement_assets.all()), [audy])
        self.assertEqual(operator.issued_stablecoin, audy)


class OperatorApiTest(APITestCase):
    url = "/api/operator/"

    def setUp(self):
        self.user = User.objects.create_user(email="investor@example.test", password="pw-12345678")

    def test_anonymous_is_refused_and_nothing_is_seeded(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertFalse(Operator.objects.exists())

    @override_settings(OPERATOR_NAME="Acme Registry")
    def test_serializer_exposes_exactly_the_public_keys(self):
        data = OperatorSerializer(Operator.get()).data

        self.assertEqual(set(data), PUBLIC_KEYS)
        self.assertEqual(data["name"], "Acme Registry")
        self.assertEqual(data["payment_instructions"], {})
        self.assertIsNone(data["issued_stablecoin"])
        self.assertEqual(data["supported_settlement_assets"], [])
        for secret in ("id", "uuid", "created_at", "updated_at", "bank_bsb", "receiving_wallet_address"):
            self.assertNotIn(secret, data)

    def test_authenticated_get_returns_the_configured_operator(self):
        audy = stablecoin()
        operator = Operator.get()
        operator.name = "Acme"
        operator.legal_name = "Acme Registry Pty Ltd"
        operator.abn = "51824753556"
        operator.contact_email = "ops@acme.test"
        operator.website = "https://acme.test"
        operator.bank_account_name = "Acme Registry Pty Ltd"
        operator.bank_bsb = "062000"
        operator.bank_account_number = "12345678"
        operator.payment_reference_prefix = "ACME"
        operator.receiving_wallet_address = WALLET
        operator.receiving_wallet_chain = ReceivingChain.BASE
        operator.issued_stablecoin = audy
        operator.save()
        operator.supported_settlement_assets.add(audy)
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), PUBLIC_JSON_KEYS)
        self.assertEqual(
            body["paymentInstructions"],
            {
                "bankAccountName": "Acme Registry Pty Ltd",
                "bankBsb": "062000",
                "bankAccountNumber": "12345678",
                "paymentReferencePrefix": "ACME",
                "receivingWalletAddress": WALLET,
                "receivingWalletChain": "base",
            },
        )
        deployment = audy.chain_deployments.get()
        expected_asset = {
            "uuid": str(audy.uuid),
            "symbol": "AUDY",
            "name": "AUDY dollar",
            "chainDeployments": [
                {
                    "uuid": str(deployment.uuid),
                    "chain": "base",
                    "contractAddress": deployment.contract_address,
                    "decimals": 6,
                    "isActive": True,
                }
            ],
        }
        self.assertEqual(body["issuedStablecoin"], expected_asset)
        self.assertEqual(body["supportedSettlementAssets"], [expected_asset])
        self.assertEqual((body["investorKycRequired"], body["issuerKycRequired"]), (True, False))
        self.assertEqual(body["deploymentMode"], "registry")

    def test_payment_instructions_carry_only_the_rails_that_are_set(self):
        operator = Operator.get()
        operator.bank_bsb = "062000"
        operator.save(update_fields=["bank_bsb"])
        self.client.force_authenticate(self.user)

        body = self.client.get(self.url).json()

        self.assertEqual(body["paymentInstructions"], {"bankBsb": "062000"})
        self.assertNotIn("receivingWalletChain", body["paymentInstructions"])
