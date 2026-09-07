from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus, CompanyType
from companies.services.company import primary_wallet_for
from operators.models import Operator
from shared.seeds.demo import (
    DEMO_ACN,
    DEMO_ADMIN_EMAIL,
    DEMO_INVESTOR_ADDRESS,
    DEMO_INVESTOR_EMAIL,
    DEMO_ISSUER_ADDRESS,
    DEMO_OWNER_EMAIL,
    DEMO_TOKEN_SYMBOL,
)
from tokens.models import ShareToken
from tokens.models.choices import ShareTokenStatus
from tokens.services.share_token_service import ShareTokenService
from users.services.eligibility import investor_eligibility
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from whitelist.models import WhitelistEntry, WhitelistStatus

User = get_user_model()


def run(**options):
    output = StringIO()
    options.setdefault("password", "pw-12345678")
    call_command("seed_demo", stdout=output, **options)
    return output.getvalue()


def signin(client, email):
    return client.post("/api/signin/", {"email": email, "password": "pw-12345678"}, format="json")


@override_settings(DEBUG=True)
class SeedDemoCommandTest(APITestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.output = run()

    def test_one_run_produces_an_owner_who_can_sign_in(self):
        response = signin(self.client, DEMO_OWNER_EMAIL)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["email"], DEMO_OWNER_EMAIL)

    def test_the_owner_lands_on_a_single_company_account(self):
        signin(self.client, DEMO_OWNER_EMAIL)

        response = self.client.get("/api/user-accounts/")

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        accounts = payload if isinstance(payload, list) else payload["results"]
        self.assertEqual([account["role"] for account in accounts], ["company"])

    def test_the_company_is_active_with_a_verified_operator_wallet(self):
        company = Company.objects.get(acn=DEMO_ACN)

        self.assertEqual(company.status, CompanyStatus.ACTIVE)
        self.assertIsNotNone(company.operator_wallet)
        self.assertEqual(primary_wallet_for(company), company.operator_wallet)
        self.assertEqual(company.operator_wallet.address, DEMO_ISSUER_ADDRESS)
        self.assertEqual(company.operator_wallet.verification_status, WALLET_VERIFICATION_STATUS_VERIFIED)

    def test_the_share_class_is_a_draft_that_passes_the_deploy_preconditions(self):
        token = ShareToken.objects.get(company__acn=DEMO_ACN, symbol=DEMO_TOKEN_SYMBOL)

        self.assertEqual(token.status, ShareTokenStatus.DRAFT)
        self.assertIsNone(token.contract_address)
        self.assertEqual(ShareTokenService.require_deployable(token), token.company.operator_wallet)

    def test_the_investor_can_sign_in_and_is_eligible(self):
        response = signin(self.client, DEMO_INVESTOR_EMAIL)
        self.assertEqual(response.status_code, 200, response.content)

        investor = User.objects.get(email=DEMO_INVESTOR_EMAIL)
        self.assertTrue(investor_eligibility(investor).is_eligible)

    def test_the_investor_wallet_has_a_whitelist_row_with_no_chain_write(self):
        entry = WhitelistEntry.objects.get(wallet__address=DEMO_INVESTOR_ADDRESS)

        self.assertEqual(entry.status, WhitelistStatus.ACTIVE)
        self.assertTrue(entry.is_whitelisted)
        self.assertIsNone(entry.add_tx_hash)

    def test_a_second_run_applies_the_password_it_prints(self):
        run(password="second-password-123")

        self.assertEqual(
            self.client.post(
                "/api/signin/",
                {"email": DEMO_OWNER_EMAIL, "password": "second-password-123"},
                format="json",
            ).status_code,
            200,
        )

    def test_a_generated_password_is_printed_and_actually_works(self):
        output = StringIO()
        call_command("seed_demo", stdout=output)

        printed = [line for line in output.getvalue().splitlines() if line.strip().startswith("password")]
        self.assertEqual(len(printed), 1, output.getvalue())
        generated = printed[0].split(maxsplit=1)[1].strip()
        self.assertNotEqual(generated, "pw-12345678")

        response = self.client.post(
            "/api/signin/",
            {"email": DEMO_OWNER_EMAIL, "password": generated},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_it_leaves_an_operator_that_already_has_payment_rails_alone(self):
        operator = Operator.get()
        operator.bank_account_name = "Real Operator"
        operator.bank_bsb = "123456"
        operator.bank_account_number = "00000001"
        operator.save()

        run()

        operator.refresh_from_db()
        self.assertEqual(operator.bank_account_name, "Real Operator")
        self.assertEqual(operator.bank_account_number, "00000001")

    def test_a_second_run_repairs_drifted_state(self):
        company = Company.objects.get(acn=DEMO_ACN)
        company.status = CompanyStatus.SUSPENDED
        company.save(update_fields=["status"])

        run()

        company.refresh_from_db()
        self.assertEqual(company.status, CompanyStatus.ACTIVE)

    def test_a_second_run_changes_nothing(self):
        before = list(Company.objects.order_by("acn").values("acn", "name", "status"))

        second = run()

        self.assertIn("0 created", second)
        self.assertEqual(list(Company.objects.order_by("acn").values("acn", "name", "status")), before)
        self.assertEqual(signin(self.client, DEMO_OWNER_EMAIL).status_code, 200)


@override_settings(DEBUG=True)
class SeedDemoAcnConflictTest(APITestCase):

    def test_it_refuses_rather_than_adopting_a_company_owned_by_someone_else(self):
        stranger = User.objects.create_user(email="stranger@example.test", password="pw-12345678")
        Company.objects.create(
            owner=stranger,
            name="Someone Else Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn=DEMO_ACN,
        )

        with self.assertRaises(CommandError):
            run()

        self.assertEqual(Company.objects.get(acn=DEMO_ACN).owner, stranger)
        self.assertFalse(User.objects.filter(email=DEMO_OWNER_EMAIL).exists())
        self.assertFalse(User.objects.filter(email=DEMO_ADMIN_EMAIL).exists())


class SeedDemoGuardTest(APITestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def test_the_command_refuses_when_debug_is_off(self):
        with self.assertRaises(CommandError) as refusal:
            run()

        self.assertIn("Refusing to seed", str(refusal.exception))
        self.assertFalse(Company.objects.exists())
        self.assertEqual(signin(self.client, DEMO_OWNER_EMAIL).status_code, 400)

    def test_force_seeds_even_when_debug_is_off(self):
        run(force=True)

        self.assertTrue(Company.objects.filter(acn=DEMO_ACN).exists())
