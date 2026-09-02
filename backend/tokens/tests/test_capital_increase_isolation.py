from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus, CompanyType
from tokens.models import (
    CapitalIncreaseRequest,
    CapitalIncreaseStatus,
    ShareToken,
    ShareTokenStatus,
    ShareTokenType,
)

User = get_user_model()


class CapitalIncreaseIsolationTest(APITestCase):
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

    def _make_token(self, company, symbol):
        self.sequence += 1
        return ShareToken.objects.create(
            company=company,
            name=f"{symbol} Ordinary Shares",
            symbol=symbol,
            token_type=ShareTokenType.ORDINARY,
            total_supply="1000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address="0x" + f"{self.sequence:040x}",
        )

    @staticmethod
    def _make_request(token, suffix):
        return CapitalIncreaseRequest.objects.create(
            token=token,
            additional_shares=100,
            new_authorized_total=1100,
            purpose=f"Capital expansion {suffix}",
            board_resolution_reference=f"BOARD-{suffix}",
            shareholder_approval_reference=f"SHARE-{suffix}",
        )

    def test_named_querysets_fail_closed_and_scope_staff_and_superuser(self):
        foreign_user = self._make_user("queryset-foreign")
        foreign_company = self._make_company(foreign_user, "Queryset Foreign")
        foreign_token = self._make_token(foreign_company, "QFR")
        foreign_request = self._make_request(foreign_token, "FOREIGN")
        actors = (
            self._make_user("queryset-staff", is_staff=True),
            User.objects.create_superuser(email="queryset-super@example.test", password="pw-12345678"),
        )

        for user in (None, AnonymousUser()):
            with self.subTest(user=user):
                self.assertFalse(CapitalIncreaseRequest.objects.visible_to_user(user).exists())
                self.assertFalse(CapitalIncreaseRequest.objects.manageable_by_user(user).exists())

        for index, actor in enumerate(actors):
            company = self._make_company(actor, f"Queryset Owner {index}")
            token = self._make_token(company, f"QO{index}")
            request = self._make_request(token, f"OWNER-{index}")

            with self.subTest(actor=actor.email):
                self.assertEqual(set(CapitalIncreaseRequest.objects.visible_to_user(actor)), {request})
                self.assertEqual(set(CapitalIncreaseRequest.objects.manageable_by_user(actor)), {request})
                self.assertNotIn(foreign_request, CapitalIncreaseRequest.objects.visible_to_user(actor))
                self.assertNotIn(foreign_request, CapitalIncreaseRequest.objects.manageable_by_user(actor))

    def test_create_binds_the_named_token_and_submit_records_the_submitter(self):
        owner = self._make_user("owner")
        token = self._make_token(self._make_company(owner, "Owner"), "OWN")
        draft = self._make_request(token, "DRAFT")
        self.client.force_authenticate(owner)

        create_response = self.client.post(
            "/api/v1/tokens/capital-increases/",
            {
                "token": str(token.uuid),
                "additionalShares": 100,
                "newAuthorizedTotal": 1100,
                "purpose": "Fund product expansion",
                "boardResolutionReference": "BOARD-API-001",
                "shareholderApprovalReference": "SHARE-API-001",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        created = CapitalIncreaseRequest.objects.get(uuid=create_response.json()["uuid"])
        self.assertEqual(created.token, token)
        self.assertEqual(created.status, CapitalIncreaseStatus.DRAFT)
        self.assertEqual(created.board_resolution_reference, "BOARD-API-001")

        submit_response = self.client.post(f"/api/v1/tokens/capital-increases/{draft.uuid}/submit/")
        self.assertEqual(submit_response.status_code, 200)
        self.assertEqual(submit_response.json()["request"]["uuid"], str(draft.uuid))
        draft.refresh_from_db()
        self.assertEqual(draft.status, CapitalIncreaseStatus.SUBMITTED)
        self.assertEqual(draft.submitted_by, owner)
        self.assertIsNotNone(draft.submitted_at)
