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

    @staticmethod
    def _response_rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    @staticmethod
    def _create_payload(token):
        return {
            "token": str(token.uuid),
            "additionalShares": 100,
            "newAuthorizedTotal": 1100,
            "purpose": "Fund product expansion",
            "boardResolutionReference": "BOARD-API-001",
            "shareholderApprovalReference": "SHARE-API-001",
        }

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

    def test_staff_and_superuser_customer_routes_are_self_scoped(self):
        foreign_user = self._make_user("routes-foreign")
        foreign_company = self._make_company(foreign_user, "Routes Foreign")
        foreign_token = self._make_token(foreign_company, "RFR")
        foreign_request = self._make_request(foreign_token, "FOREIGN")
        actors = (
            self._make_user("routes-staff", is_staff=True),
            User.objects.create_superuser(email="routes-super@example.test", password="pw-12345678"),
        )

        for index, actor in enumerate(actors):
            company = self._make_company(actor, f"Routes Owner {index}")
            token = self._make_token(company, f"RO{index}")
            own_request = self._make_request(token, f"OWNER-{index}")
            self.client.force_authenticate(actor)

            with self.subTest(actor=actor.email):
                list_response = self.client.get("/api/v1/tokens/capital-increases/")
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(
                    {row["uuid"] for row in self._response_rows(list_response)},
                    {str(own_request.uuid)},
                )

                detail_response = self.client.get(f"/api/v1/tokens/capital-increases/{own_request.uuid}/")
                self.assertEqual(detail_response.status_code, 200)
                self.assertEqual(detail_response.json()["uuid"], str(own_request.uuid))

                create_response = self.client.post(
                    "/api/v1/tokens/capital-increases/",
                    self._create_payload(token),
                    format="json",
                )
                self.assertEqual(create_response.status_code, 201)
                created_request = CapitalIncreaseRequest.objects.get(uuid=create_response.json()["uuid"])
                self.assertEqual(created_request.token, token)
                self.assertEqual(created_request.additional_shares, 100)
                self.assertEqual(created_request.new_authorized_total, 1100)
                self.assertEqual(created_request.board_resolution_reference, "BOARD-API-001")

                submit_response = self.client.post(f"/api/v1/tokens/capital-increases/{own_request.uuid}/submit/")
                self.assertEqual(submit_response.status_code, 200)
                own_request.refresh_from_db()
                self.assertEqual(own_request.status, CapitalIncreaseStatus.SUBMITTED)
                self.assertEqual(own_request.submitted_by, actor)
                self.assertIsNotNone(own_request.submitted_at)

                original_foreign_values = {
                    "additional_shares": foreign_request.additional_shares,
                    "new_authorized_total": foreign_request.new_authorized_total,
                    "purpose": foreign_request.purpose,
                    "status": foreign_request.status,
                    "submitted_by_id": foreign_request.submitted_by_id,
                }
                foreign_detail = self.client.get(f"/api/v1/tokens/capital-increases/{foreign_request.uuid}/")
                foreign_update = self.client.patch(
                    f"/api/v1/tokens/capital-increases/{foreign_request.uuid}/",
                    {
                        "additionalShares": 999,
                        "newAuthorizedTotal": 2000,
                        "purpose": "Unauthorized change",
                    },
                    format="json",
                )
                foreign_delete = self.client.delete(f"/api/v1/tokens/capital-increases/{foreign_request.uuid}/")
                foreign_submit = self.client.post(f"/api/v1/tokens/capital-increases/{foreign_request.uuid}/submit/")
                self.assertEqual(
                    [
                        foreign_detail.status_code,
                        foreign_update.status_code,
                        foreign_delete.status_code,
                        foreign_submit.status_code,
                    ],
                    [404] * 4,
                )
                foreign_request.refresh_from_db()
                self.assertEqual(
                    {
                        "additional_shares": foreign_request.additional_shares,
                        "new_authorized_total": foreign_request.new_authorized_total,
                        "purpose": foreign_request.purpose,
                        "status": foreign_request.status,
                        "submitted_by_id": foreign_request.submitted_by_id,
                    },
                    original_foreign_values,
                )

                foreign_request_count = CapitalIncreaseRequest.objects.filter(token=foreign_token).count()
                foreign_create = self.client.post(
                    "/api/v1/tokens/capital-increases/",
                    self._create_payload(foreign_token),
                    format="json",
                )
                self.assertEqual(foreign_create.status_code, 404)
                self.assertEqual(
                    CapitalIncreaseRequest.objects.filter(token=foreign_token).count(),
                    foreign_request_count,
                )
