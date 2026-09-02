from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus, CompanyType
from tokens.models import (
    IssuanceStatus,
    ShareIssuance,
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

    @staticmethod
    def _response_rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

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
                self.assertFalse(ShareToken.objects.visible_to_user(user).exists())
                self.assertFalse(ShareToken.objects.manageable_by_user(user).exists())
                self.assertFalse(ShareIssuanceRequest.objects.visible_to_user(user).exists())
                self.assertFalse(ShareIssuanceRequest.objects.manageable_by_user(user).exists())

        for index, actor in enumerate(actors):
            company = self._make_company(actor, f"Queryset Owner {index}")
            token = self._make_token(company, f"QO{index}")
            request = self._make_issuance_request(token, actor, "0x" + f"{index + 2:x}" * 40)

            with self.subTest(actor=actor.email):
                self.assertEqual(set(ShareToken.objects.visible_to_user(actor)), {token})
                self.assertEqual(set(ShareToken.objects.manageable_by_user(actor)), {token})
                self.assertEqual(set(ShareIssuanceRequest.objects.visible_to_user(actor)), {request})
                self.assertEqual(set(ShareIssuanceRequest.objects.manageable_by_user(actor)), {request})
                self.assertNotIn(foreign_token, ShareToken.objects.visible_to_user(actor))
                self.assertNotIn(foreign_request, ShareIssuanceRequest.objects.visible_to_user(actor))

    def test_staff_and_superuser_customer_crud_is_self_scoped(self):
        foreign_user = self._make_user("crud-foreign")
        foreign_company = self._make_company(foreign_user, "CRUD Foreign")
        foreign_token = self._make_token(foreign_company, "CFR")
        actors = (
            self._make_user("crud-staff", is_staff=True),
            User.objects.create_superuser(email="crud-super@example.test", password="pw-12345678"),
        )

        for index, actor in enumerate(actors):
            company = self._make_company(actor, f"CRUD Owner {index}")
            own_token = self._make_token(company, f"CO{index}")
            disposable_token = self._make_token(company, f"CD{index}")
            self.client.force_authenticate(actor)

            with self.subTest(actor=actor.email):
                list_response = self.client.get("/api/v1/tokens/")
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(
                    {row["uuid"] for row in self._response_rows(list_response)},
                    {str(own_token.uuid), str(disposable_token.uuid)},
                )

                own_detail = self.client.get(f"/api/v1/tokens/{own_token.uuid}/")
                self.assertEqual(own_detail.status_code, 200)
                self.assertEqual(own_detail.json()["uuid"], str(own_token.uuid))

                foreign_count = foreign_company.tokens.count()
                payload = {
                    "name": f"Created by {actor.email}",
                    "symbol": f"N{chr(65 + index)}W",
                    "tokenType": ShareTokenType.ORDINARY,
                    "totalSupply": "1000",
                    "decimals": 0,
                    "isTransferable": True,
                    "isDivisible": False,
                }
                foreign_create = self.client.post(
                    "/api/v1/tokens/", {**payload, "company": str(foreign_company.uuid)}, format="json"
                )
                self.assertEqual(foreign_create.status_code, 400)
                self.assertEqual(foreign_company.tokens.count(), foreign_count)

                create_response = self.client.post(
                    "/api/v1/tokens/", {**payload, "company": str(company.uuid)}, format="json"
                )
                self.assertEqual(create_response.status_code, 201)
                created_token = ShareToken.objects.get(uuid=create_response.json()["uuid"])
                self.assertEqual(created_token.company, company)

                delete_response = self.client.delete(f"/api/v1/tokens/{disposable_token.uuid}/")
                self.assertEqual(delete_response.status_code, 204)
                self.assertFalse(ShareToken.objects.filter(uuid=disposable_token.uuid).exists())

                original_name = foreign_token.name
                foreign_detail = self.client.get(f"/api/v1/tokens/{foreign_token.uuid}/")
                foreign_update = self.client.patch(
                    f"/api/v1/tokens/{foreign_token.uuid}/",
                    {"name": "Unauthorized rename"},
                    format="json",
                )
                foreign_delete = self.client.delete(f"/api/v1/tokens/{foreign_token.uuid}/")
                self.assertEqual(foreign_detail.status_code, 404)
                self.assertEqual(foreign_update.status_code, 404)
                self.assertEqual(foreign_delete.status_code, 404)
                foreign_token.refresh_from_db()
                self.assertEqual(foreign_token.name, original_name)

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

    @patch("tokens.views.share_token.WhitelistService")
    @patch("tokens.views.share_token.ShareTokenService")
    @patch("tokens.views.share_token.deploy_share_token_task.defer")
    @patch("companies.models.Company.get_primary_wallet")
    def test_staff_and_superuser_custom_actions_are_self_scoped(
        self,
        primary_wallet,
        deploy_task,
        service_class,
        whitelist_class,
    ):
        primary_wallet.return_value = object()
        foreign_user = self._make_user("actions-foreign")
        foreign_company = self._make_company(foreign_user, "Actions Foreign")
        foreign_draft = self._make_token(foreign_company, "AFD")
        foreign_deployed = self._make_token(foreign_company, "AFL", ShareTokenStatus.DEPLOYED)
        foreign_paused = self._make_token(foreign_company, "AFP", ShareTokenStatus.PAUSED)
        actors = (
            self._make_user("actions-staff", is_staff=True),
            User.objects.create_superuser(email="actions-super@example.test", password="pw-12345678"),
        )
        recipient = "0x" + "9" * 40
        issue_payload = {
            "recipient": recipient,
            "amount": 7,
            "reason": "Owner request",
            "issuanceType": "additional",
        }

        for index, actor in enumerate(actors):
            company = self._make_company(actor, f"Actions Owner {index}")
            own_draft = self._make_token(company, f"AD{index}")
            own_lifecycle = self._make_token(company, f"AL{index}", ShareTokenStatus.DEPLOYED)
            own_deployed = self._make_token(company, f"AO{index}", ShareTokenStatus.DEPLOYED)
            own_request = self._make_issuance_request(own_deployed, actor, recipient)
            own_issuance = ShareIssuance.objects.create(
                token=own_deployed,
                recipient_address=recipient,
                amount="5",
                reason="Completed owner issuance",
                status=IssuanceStatus.COMPLETED,
                initiated_by=actor,
            )
            holders = [
                {
                    "address": recipient,
                    "name": None,
                    "balance": "5",
                    "source": "issuances",
                    "percentage": 100.0,
                }
            ]
            eligibility = {
                "can_receive": True,
                "db_whitelisted": True,
                "on_chain_whitelisted": False,
                "investor_type": "retail",
                "investor_type_display": "Retail",
            }
            service = service_class.return_value
            service.create_issuance_request.return_value = own_request
            service.get_token_holders.return_value = holders
            whitelist = whitelist_class.return_value
            whitelist.get_receive_eligibility.return_value = eligibility
            self.client.force_authenticate(actor)

            with self.subTest(actor=actor.email):
                deploy_response = self.client.post(f"/api/v1/tokens/{own_draft.uuid}/deploy/")
                self.assertEqual(deploy_response.status_code, 200)
                own_draft.refresh_from_db()
                self.assertEqual(own_draft.status, ShareTokenStatus.DEPLOYING)
                deploy_task.assert_called_once_with(token_uuid=str(own_draft.uuid))

                pause_response = self.client.post(f"/api/v1/tokens/{own_lifecycle.uuid}/pause/")
                self.assertEqual(pause_response.status_code, 200)
                own_lifecycle.refresh_from_db()
                self.assertEqual(own_lifecycle.status, ShareTokenStatus.PAUSED)

                unpause_response = self.client.post(f"/api/v1/tokens/{own_lifecycle.uuid}/unpause/")
                self.assertEqual(unpause_response.status_code, 200)
                own_lifecycle.refresh_from_db()
                self.assertEqual(own_lifecycle.status, ShareTokenStatus.DEPLOYED)

                issue_response = self.client.post(
                    f"/api/v1/tokens/{own_deployed.uuid}/issue/",
                    issue_payload,
                    format="json",
                )
                self.assertEqual(issue_response.status_code, 201)
                self.assertEqual(issue_response.json()["issuanceRequest"]["uuid"], str(own_request.uuid))
                service.create_issuance_request.assert_called_once_with(
                    token=own_deployed,
                    recipient=recipient,
                    amount=7,
                    user=actor,
                    reason="Owner request",
                    issuance_type="additional",
                )

                issuances_response = self.client.get(f"/api/v1/tokens/{own_deployed.uuid}/issuances/")
                self.assertEqual(issuances_response.status_code, 200)
                self.assertEqual(
                    {row["uuid"] for row in self._response_rows(issuances_response)},
                    {str(own_issuance.uuid)},
                )

                holders_response = self.client.get(f"/api/v1/tokens/{own_deployed.uuid}/holders/")
                self.assertEqual(holders_response.status_code, 200)
                self.assertEqual(holders_response.json()["holders"], holders)
                service.get_token_holders.assert_called_once_with(own_deployed)

                can_receive_response = self.client.get(f"/api/v1/tokens/{own_deployed.uuid}/can-receive/{recipient}/")
                self.assertEqual(can_receive_response.status_code, 200)
                self.assertTrue(can_receive_response.json()["canReceive"])
                whitelist.get_receive_eligibility.assert_called_once_with(recipient)

                primary_wallet.reset_mock()
                deploy_task.reset_mock()
                service_class.reset_mock()
                whitelist_class.reset_mock()

                foreign_responses = (
                    self.client.post(f"/api/v1/tokens/{foreign_draft.uuid}/deploy/"),
                    self.client.post(f"/api/v1/tokens/{foreign_deployed.uuid}/pause/"),
                    self.client.post(f"/api/v1/tokens/{foreign_paused.uuid}/unpause/"),
                    self.client.post(
                        f"/api/v1/tokens/{foreign_deployed.uuid}/issue/",
                        issue_payload,
                        format="json",
                    ),
                    self.client.get(f"/api/v1/tokens/{foreign_deployed.uuid}/issuances/"),
                    self.client.get(f"/api/v1/tokens/{foreign_deployed.uuid}/holders/"),
                    self.client.get(f"/api/v1/tokens/{foreign_deployed.uuid}/can-receive/{recipient}/"),
                )
                self.assertEqual([response.status_code for response in foreign_responses], [404] * 7)
                primary_wallet.assert_not_called()
                deploy_task.assert_not_called()
                service_class.assert_not_called()
                whitelist_class.assert_not_called()

                foreign_draft.refresh_from_db()
                foreign_deployed.refresh_from_db()
                foreign_paused.refresh_from_db()
                self.assertEqual(foreign_draft.status, ShareTokenStatus.DRAFT)
                self.assertEqual(foreign_deployed.status, ShareTokenStatus.DEPLOYED)
                self.assertEqual(foreign_paused.status, ShareTokenStatus.PAUSED)

            primary_wallet.reset_mock()
            deploy_task.reset_mock()
            service_class.reset_mock()
            whitelist_class.reset_mock()

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
