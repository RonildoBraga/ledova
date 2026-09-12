from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus, CompanyType
from shared.tests.under_the_policies import what_the_policies_admit_to
from tokens.models import (
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
    ShareTokenType,
)

User = get_user_model()


class ShareTokenIsolationTest(APITestCase):
    def setUp(self):
        self.sequence = 0

    def _make_user(self, label, **privileges):
        return User.objects.create_user(
            email=f"{label}@example.test",
            password="pw-12345678",
            is_active=True,
            is_email_verified=True,
            **privileges,
        )

    def _make_company(self, owner, label):
        self.sequence += 1
        return Company.objects.create(
            owner=owner,
            name=f"{label} Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn=f"{self.sequence:09d}",
            status=CompanyStatus.ACTIVE,
        )

    def _make_token(self, company, symbol, status=ShareTokenStatus.DRAFT):
        self.sequence += 1
        contract_address = None
        if status in (ShareTokenStatus.DEPLOYED, ShareTokenStatus.PAUSED):
            contract_address = "0x" + f"{self.sequence:040x}"
        return ShareToken.objects.create(
            company=company,
            name=f"{symbol} Ordinary Shares",
            symbol=symbol,
            token_type=ShareTokenType.ORDINARY,
            total_supply="1000000",
            status=status,
            contract_address=contract_address,
        )

    def _make_issuance_request(self, token, user, address):
        return ShareIssuanceRequest.objects.create(
            token=token,
            recipient_address=address,
            amount=7,
            reason="Owner request",
            submitted_by=user,
        )

    def test_named_querysets_fail_closed_and_scope_staff_and_superuser(self):
        foreign_user = self._make_user("queryset-foreign")
        foreign_company = self._make_company(foreign_user, "Queryset Foreign")
        foreign_token = self._make_token(foreign_company, "QFR")
        foreign_request = self._make_issuance_request(foreign_token, foreign_user, "0x" + "1" * 40)

        actors = (
            self._make_user("queryset-staff", is_staff=True),
            User.objects.create_superuser(email="queryset-super@example.test", password="pw-12345678"),
        )

        for user in (None, AnonymousUser()):
            with self.subTest(user=user):
                self.assertFalse(what_the_policies_admit_to(user, ShareToken).exists())
                self.assertFalse(what_the_policies_admit_to(user, ShareToken).exists())
                self.assertFalse(what_the_policies_admit_to(user, ShareIssuanceRequest).exists())
                self.assertFalse(what_the_policies_admit_to(user, ShareIssuanceRequest).exists())

        for index, actor in enumerate(actors):
            company = self._make_company(actor, f"Queryset Owner {index}")
            token = self._make_token(company, f"QO{index}")
            request = self._make_issuance_request(token, actor, "0x" + f"{index + 2:x}" * 40)

            with self.subTest(actor=actor.email):
                self.assertEqual(set(what_the_policies_admit_to(actor, ShareToken)), {token})
                self.assertEqual(set(what_the_policies_admit_to(actor, ShareToken)), {token})
                self.assertEqual(set(what_the_policies_admit_to(actor, ShareIssuanceRequest)), {request})
                self.assertEqual(set(what_the_policies_admit_to(actor, ShareIssuanceRequest)), {request})
                self.assertNotIn(foreign_token, what_the_policies_admit_to(actor, ShareToken))
                self.assertNotIn(foreign_request, what_the_policies_admit_to(actor, ShareIssuanceRequest))

    def test_unaffiliated_privileged_users_cannot_create_tokens(self):
        foreign_user = self._make_user("crud-foreign")
        foreign_company = self._make_company(foreign_user, "CRUD Foreign")
        unaffiliated_actors = (
            self._make_user("unaffiliated-staff", is_staff=True),
            User.objects.create_superuser(email="unaffiliated-super@example.test", password="pw-12345678"),
        )
        for index, actor in enumerate(unaffiliated_actors):
            self.client.force_authenticate(actor)
            token_count = ShareToken.objects.count()
            response = self.client.post(
                "/api/v1/tokens/",
                {
                    "company": str(foreign_company.uuid),
                    "name": "Foreign company token",
                    "symbol": f"U{chr(65 + index)}A",
                    "tokenType": ShareTokenType.ORDINARY,
                    "totalSupply": "1000",
                },
                format="json",
            )

            with self.subTest(actor=actor.email):
                self.assertEqual(response.status_code, 403)
                self.assertEqual(ShareToken.objects.count(), token_count)

    def test_multi_company_owner_must_name_the_issuing_company(self):
        owner = self._make_user("multi-owner")
        first = self._make_company(owner, "First")
        second = self._make_company(owner, "Second")
        self.client.force_authenticate(owner)
        payload = {"name": "Second token", "symbol": "SEC", "tokenType": ShareTokenType.ORDINARY, "totalSupply": "1000"}

        ambiguous = self.client.post("/api/v1/tokens/", payload, format="json")
        self.assertEqual(ambiguous.status_code, 400)
        self.assertIn("company", ambiguous.json())
        self.assertEqual(ShareToken.objects.count(), 0)

        explicit = self.client.post("/api/v1/tokens/", {**payload, "company": str(second.uuid)}, format="json")
        self.assertEqual(explicit.status_code, 201)
        self.assertEqual(ShareToken.objects.get(symbol="SEC").company, second)

        foreign = self.client.post(
            "/api/v1/tokens/",
            {**payload, "symbol": "FOR", "company": str(self._make_company(self._make_user("other"), "Other").uuid)},
            format="json",
        )
        self.assertEqual(foreign.status_code, 400)
        self.assertFalse(ShareToken.objects.filter(symbol="FOR").exists())

        single = self._make_user("single-owner")
        only = self._make_company(single, "Only")
        self.client.force_authenticate(single)
        defaulted = self.client.post("/api/v1/tokens/", {**payload, "symbol": "ONE"}, format="json")
        self.assertEqual(defaulted.status_code, 201)
        self.assertEqual(ShareToken.objects.get(symbol="ONE").company, only)
        self.assertNotEqual(first, only)
