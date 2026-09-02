"""Application-level company isolation through the live owner relationship."""

from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APITestCase

from companies.models import Company, CompanyDocument
from tokens.models import (
    CapitalIncreaseRequest,
    CapitalIncreaseStatus,
    IssuanceStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
    TransferOrder,
)
from tokens.models.choices import TransferOrderStatus, TransferOrderType
from tokens.serializers import ShareTokenCreateSerializer
from users.models import UserAccount, UserProfile
from wallets.models import Wallet
from whitelist.models import WhitelistEntry

User = get_user_model()


class CompanyLiveAuthorizationTest(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-company@example.test", password="pw-12345678")
        self.bob = User.objects.create_user(email="bob-company@example.test", password="pw-12345678")
        self.staff = User.objects.create_user(
            email="staff-company@example.test",
            password="pw-12345678",
            is_staff=True,
        )
        self.superuser = User.objects.create_user(
            email="super-company@example.test",
            password="pw-12345678",
            is_superuser=True,
            is_staff=True,
        )
        self.company = Company.objects.create(
            owner=self.alice,
            name="Alice Holdings Pty Ltd",
            trading_name="Alice Holdings",
            company_type="pty",
            acn="111111111",
            status="active",
            phone="0400000000",
            address_line_1="Private address",
        )
        self.document = CompanyDocument.objects.create(
            company=self.company,
            document_type="director_id",
            name="Director identity",
            external_url="https://private.example.test/director-id",
            file_size=123,
            mime_type="application/pdf",
        )
        self.token = ShareToken.objects.create(
            company=self.company,
            name="Alice Ordinary",
            symbol="ALICE",
            total_supply="1000",
        )
        self.capital_increase = CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=100,
            new_authorized_total=1100,
            purpose="Testing",
            board_resolution_reference="BOARD-1",
        )
        self.issuance_request = ShareIssuanceRequest.objects.create(
            token=self.token,
            recipient_address="0x" + "a" * 40,
            amount=10,
            reason="Testing",
        )

        profile = UserProfile.objects.create(user=self.alice)
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account,
            address="0x" + "a" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )
        self.order = TransferOrder.objects.create(
            token=self.token,
            order_type=TransferOrderType.SELL,
            status=TransferOrderStatus.OPEN,
            wallet=wallet,
            owner_account=account,
            wallet_address=wallet.address,
            quantity=10,
            price_per_share=Decimal("1.00"),
        )

    def test_owner_is_live_authority_for_company_and_all_derived_resources(self):
        self.assertNotIn(self.company, Company.objects.visible_to_user(self.bob))
        self.assertNotIn(self.company, Company.objects.manageable_by_user(self.bob))

        Company.objects.filter(pk=self.company.pk).update(owner=self.bob)
        self.company.refresh_from_db()

        former_owner_querysets = (
            Company.objects.visible_to_user(self.alice),
            Company.objects.manageable_by_user(self.alice),
            CompanyDocument.objects.visible_to_user(self.alice),
            CompanyDocument.objects.manageable_by_user(self.alice),
            ShareToken.objects.visible_to_user(self.alice),
            ShareToken.objects.manageable_by_user(self.alice),
            CapitalIncreaseRequest.objects.visible_to_user(self.alice),
            CapitalIncreaseRequest.objects.manageable_by_user(self.alice),
            ShareIssuanceRequest.objects.visible_to_user(self.alice),
            ShareIssuanceRequest.objects.manageable_by_user(self.alice),
            TransferOrder.objects.for_token_visible_to_user(self.alice),
        )
        for queryset in former_owner_querysets:
            with self.subTest(model=queryset.model._meta.label):
                self.assertFalse(queryset.exists())

        current_owner_querysets = (
            Company.objects.visible_to_user(self.bob),
            Company.objects.manageable_by_user(self.bob),
            CompanyDocument.objects.visible_to_user(self.bob),
            CompanyDocument.objects.manageable_by_user(self.bob),
            ShareToken.objects.visible_to_user(self.bob),
            ShareToken.objects.manageable_by_user(self.bob),
            CapitalIncreaseRequest.objects.visible_to_user(self.bob),
            CapitalIncreaseRequest.objects.manageable_by_user(self.bob),
            ShareIssuanceRequest.objects.visible_to_user(self.bob),
            ShareIssuanceRequest.objects.manageable_by_user(self.bob),
            TransferOrder.objects.for_token_visible_to_user(self.bob),
        )
        for queryset in current_owner_querysets:
            with self.subTest(model=queryset.model._meta.label):
                self.assertTrue(queryset.exists())

        for user, expected in ((self.alice, set()), (self.bob, {self.company.uuid})):
            serializer = ShareTokenCreateSerializer(context={"request": SimpleNamespace(user=user)})
            self.assertEqual(set(serializer.fields["company"].queryset.values_list("uuid", flat=True)), expected)

    def test_staff_and_superuser_customer_routes_follow_company_ownership(self):
        for user in (None, AnonymousUser()):
            with self.subTest(user=user):
                self.assertFalse(Company.objects.visible_to_user(user).exists())
                self.assertFalse(Company.objects.manageable_by_user(user).exists())
                self.assertFalse(CompanyDocument.objects.visible_to_user(user).exists())
                self.assertFalse(CompanyDocument.objects.manageable_by_user(user).exists())

        for index, privileged_user in enumerate((self.staff, self.superuser), start=4):
            company = Company.objects.create(
                owner=privileged_user,
                name=f"Privileged Company {index}",
                company_type="pty",
                acn=str(index) * 9,
                status="active",
            )
            document = CompanyDocument.objects.create(
                company=company,
                document_type="asic",
                name=f"Privileged ASIC {index}",
                external_url=f"https://private.example.test/privileged-{index}",
                file_size=123,
                mime_type="application/pdf",
            )

            with self.subTest(user=privileged_user.email):
                self.assertEqual(set(Company.objects.visible_to_user(privileged_user)), {company})
                self.assertEqual(set(Company.objects.manageable_by_user(privileged_user)), {company})
                self.assertEqual(set(CompanyDocument.objects.visible_to_user(privileged_user)), {document})
                self.assertEqual(set(CompanyDocument.objects.manageable_by_user(privileged_user)), {document})

                self.client.force_authenticate(privileged_user)
                list_response = self.client.get("/api/v1/companies/")
                own_response = self.client.get(f"/api/v1/companies/{company.uuid}/")
                foreign_response = self.client.get(f"/api/v1/companies/{self.company.uuid}/")
                foreign_update = self.client.patch(
                    f"/api/v1/companies/{self.company.uuid}/",
                    {"name": "Stolen"},
                    format="json",
                )
                own_documents = self.client.get(f"/api/v1/companies/{company.uuid}/documents/")
                foreign_documents = self.client.get(f"/api/v1/companies/{self.company.uuid}/documents/")

                rows = list_response.json().get("results", list_response.json())
                self.assertEqual({row["uuid"] for row in rows}, {str(company.uuid)})
                self.assertEqual(own_response.status_code, 200)
                self.assertEqual(foreign_response.status_code, 404)
                self.assertEqual(foreign_update.status_code, 404)
                self.assertEqual(own_documents.status_code, 200)
                document_rows = own_documents.json().get("results", own_documents.json())
                self.assertEqual({row["uuid"] for row in document_rows}, {str(document.uuid)})
                self.assertEqual(foreign_documents.status_code, 404)

        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Alice Holdings Pty Ltd")

    def test_company_stats_are_exactly_self_scoped_for_regular_and_privileged_owners(self):
        foreign_company = Company.objects.create(
            owner=self.bob,
            name="Foreign Stats Company",
            company_type="pty",
            acn="888888888",
            status="active",
        )
        actor_cases = []
        for index, actor in enumerate((self.alice, self.staff, self.superuser), start=5):
            if actor == self.alice:
                company = self.company
            else:
                company = Company.objects.create(
                    owner=actor,
                    name=f"Stats Company {index}",
                    company_type="pty",
                    acn=str(index) * 9,
                    status="active",
                )
            token = ShareToken.objects.create(
                company=company,
                name=f"Stats Token {index}",
                symbol=f"ST{index}",
                total_supply="1000",
                status=ShareTokenStatus.DEPLOYED,
            )
            ShareIssuance.objects.create(
                token=token,
                recipient_address="0x" + f"{index:x}" * 40,
                amount="100",
                reason="Stats coverage",
                status=IssuanceStatus.COMPLETED,
                initiated_by=actor,
            )
            CapitalIncreaseRequest.objects.create(
                token=token,
                additional_shares=100,
                new_authorized_total=1100,
                purpose="Stats coverage",
                board_resolution_reference=f"BOARD-STATS-{index}",
                status=CapitalIncreaseStatus.SUBMITTED,
            )
            actor_cases.append((actor, company))

        expected = {
            "totalTokens": 1,
            "totalShareholders": 1,
            "pendingActions": 1,
            "pendingCapitalIncreases": 1,
        }
        baseline = {}
        for actor, company in actor_cases:
            self.client.force_authenticate(actor)
            response = self.client.get(f"/api/v1/companies/{company.uuid}/stats/")
            foreign_response = self.client.get(f"/api/v1/companies/{foreign_company.uuid}/stats/")

            with self.subTest(actor=actor.email, phase="baseline"):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), expected)
                self.assertEqual(foreign_response.status_code, 404)
                baseline[actor.pk] = response.json()

        foreign_profile = UserProfile.objects.create(user=self.bob)
        foreign_account = UserAccount.objects.create(account_number="FOREIGN-STATS")
        foreign_account.user_profiles.add(foreign_profile)
        foreign_wallet = Wallet.objects.create(
            user_account=foreign_account,
            address="0x" + "f" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )
        WhitelistEntry.objects.create(wallet=foreign_wallet, is_whitelisted=True)

        for actor, company in actor_cases:
            self.client.force_authenticate(actor)
            response = self.client.get(f"/api/v1/companies/{company.uuid}/stats/")

            with self.subTest(actor=actor.email, phase="foreign-whitelist"):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), baseline[actor.pk])
                self.assertEqual(set(response.json()), set(expected))


class CompanyEndpointIsolationTest(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-company-api@example.test", password="pw-12345678")
        self.bob = User.objects.create_user(email="bob-company-api@example.test", password="pw-12345678")
        self.alice_company = Company.objects.create(
            owner=self.alice,
            name="Alice Company",
            company_type="pty",
            acn="222222222",
            status="active",
        )
        self.bob_company = Company.objects.create(
            owner=self.bob,
            name="Bob Company",
            company_type="pty",
            acn="333333333",
            status="active",
            phone="0411111111",
            address_line_1="Bob private address",
        )
        self.bob_document = CompanyDocument.objects.create(
            company=self.bob_company,
            document_type="bank_statement",
            name="Bob bank statement",
            external_url="https://private.example.test/bob-bank",
            file_size=456,
            mime_type="application/pdf",
        )
        self.alice_document = CompanyDocument.objects.create(
            company=self.alice_company,
            document_type="asic",
            name="Alice ASIC extract",
            external_url="https://owner.example.test/alice-asic",
            file_size=321,
            mime_type="application/pdf",
        )

    @staticmethod
    def _rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    def test_authenticated_company_routes_do_not_cross_owner_boundary(self):
        self.client.force_authenticate(self.alice)

        list_response = self.client.get("/api/v1/companies/")
        self.assertEqual(list_response.status_code, 200)
        returned = {row["uuid"] for row in self._rows(list_response)}
        self.assertIn(str(self.alice_company.uuid), returned)
        self.assertNotIn(str(self.bob_company.uuid), returned)

        cases = (
            ("get", f"/api/v1/companies/{self.bob_company.uuid}/", None),
            ("get", f"/api/v1/companies/{self.bob_company.uuid}/stats/", None),
            ("get", f"/api/v1/companies/{self.bob_company.uuid}/application-status/", None),
            ("patch", f"/api/v1/companies/{self.bob_company.uuid}/", {"name": "Stolen"}),
            ("delete", f"/api/v1/companies/{self.bob_company.uuid}/", None),
            ("post", f"/api/v1/companies/{self.bob_company.uuid}/submit/", {}),
            ("post", f"/api/v1/companies/{self.bob_company.uuid}/resubmit/", {"response": "x"}),
            ("post", f"/api/v1/companies/{self.bob_company.uuid}/withdraw/", {}),
        )
        for method, url, payload in cases:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, 404)

        self.bob_company.refresh_from_db()
        self.assertEqual(self.bob_company.name, "Bob Company")

    def test_nested_company_documents_require_access_to_the_parent(self):
        self.client.force_authenticate(self.alice)
        own_collection_url = f"/api/v1/companies/{self.alice_company.uuid}/documents/"
        own_collection = self.client.get(own_collection_url)
        own_detail = self.client.get(f"{own_collection_url}{self.alice_document.uuid}/")
        self.assertEqual(own_collection.status_code, 200)
        self.assertEqual(own_detail.status_code, 200)
        self.assertEqual(
            {row["uuid"] for row in self._rows(own_collection)},
            {str(self.alice_document.uuid)},
        )

        collection_url = f"/api/v1/companies/{self.bob_company.uuid}/documents/"
        detail_url = f"{collection_url}{self.bob_document.uuid}/"

        for method, url, payload in (
            ("get", collection_url, None),
            ("post", collection_url, {}),
            ("get", detail_url, None),
            ("delete", detail_url, None),
        ):
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, 404)

        self.assertTrue(CompanyDocument.objects.filter(pk=self.bob_document.pk).exists())

    def test_anonymous_company_detail_and_acn_lookup_are_public_safe(self):
        inactive_company = Company.objects.create(
            owner=self.bob,
            name="Bob Inactive Company",
            company_type="pty",
            acn="999999999",
            status="draft",
        )

        list_response = self.client.get("/api/v1/companies/")
        self.assertEqual(list_response.status_code, 200)
        returned = {row["uuid"] for row in self._rows(list_response)}
        self.assertIn(str(self.bob_company.uuid), returned)
        self.assertNotIn(str(inactive_company.uuid), returned)

        for url in (
            f"/api/v1/companies/{self.bob_company.uuid}/",
            f"/api/v1/companies/acn/{self.bob_company.acn}/",
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["uuid"], str(self.bob_company.uuid))
                for private_field in (
                    "documents",
                    "email",
                    "phone",
                    "addressLine1",
                    "infoRequestReason",
                    "primaryContact",
                ):
                    self.assertNotIn(private_field, body)
                self.assertNotIn(self.bob_document.external_url, str(body))

        for url in (
            f"/api/v1/companies/{inactive_company.uuid}/",
            f"/api/v1/companies/acn/{inactive_company.acn}/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_explicit_admin_actions_keep_global_scope(self):
        staff = User.objects.create_user(
            email="company-admin@example.test",
            password="pw-12345678",
            is_staff=True,
        )
        self.client.force_authenticate(staff)

        api_key_response = self.client.get(f"/api/v1/companies/{self.bob_company.uuid}/api-key/")
        regenerate_response = self.client.post(f"/api/v1/companies/{self.bob_company.uuid}/api-key/")
        status_response = self.client.post(
            f"/api/v1/companies/{self.bob_company.uuid}/status/",
            {"status": "warning", "reason": "Administrative review"},
            format="json",
        )

        self.assertEqual(api_key_response.status_code, 200)
        self.assertEqual(regenerate_response.status_code, 200)
        self.assertEqual(status_response.status_code, 200)
        self.bob_company.refresh_from_db()
        self.assertEqual(self.bob_company.status, "warning")

        self.client.force_authenticate(self.alice)
        self.assertEqual(
            self.client.get(f"/api/v1/companies/{self.bob_company.uuid}/api-key/").status_code,
            403,
        )

        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(f"/api/v1/companies/{self.bob_company.uuid}/api-key/").status_code,
            401,
        )
