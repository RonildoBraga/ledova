from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus
from integrations.base_chain.exceptions import BaseChainConnectionError
from shared.tests.tenants import make_tenant
from tokens.exceptions import TokenPauseFailedException
from tokens.models import (
    IssuanceStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareTokenStatus,
)
from wallets.models import Wallet

RECIPIENT = "0x" + "9" * 40
HOLDERS = [{"address": RECIPIENT, "name": None, "balance": "5", "source": "issuances", "percentage": 100.0}]


class ShareTokenActionTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("owner")
        self.client.force_authenticate(self.tenant.user)

    def _activate(self):
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)

    @override_settings(BLOCKCHAIN_OPERATOR_KEY="0xkey")
    @patch("tokens.services.share_token_service.get_base_chain_client")
    @patch("tokens.tasks.deploy_share_token_task")
    def test_deploy_pause_and_unpause_move_status(self, deploy_task, chain_client):
        self._activate()
        draft, deployed = self.tenant.token, self.tenant.deployed_token
        chain = chain_client.return_value
        contract = chain.load_contract.return_value
        contract.functions.paused.return_value.call.side_effect = [False, True]
        chain.send_transaction.return_value = ("0xtx", {"blockNumber": 1, "gasUsed": 1})

        response = self.client.post(f"/api/v1/tokens/{draft.uuid}/deploy/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Token deployment initiated.")
        self.assertEqual(response.json()["token"]["status"], ShareTokenStatus.DEPLOYING)
        draft.refresh_from_db()
        self.assertEqual(draft.status, ShareTokenStatus.DEPLOYING)
        deploy_task.defer.assert_called_once_with(token_uuid=str(draft.uuid))

        paused = self.client.post(f"/api/v1/tokens/{deployed.uuid}/pause/")
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["token"]["status"], ShareTokenStatus.PAUSED)
        deployed.refresh_from_db()
        self.assertEqual(deployed.status, ShareTokenStatus.PAUSED)
        self.assertEqual(chain.send_transaction.call_args.args[0], contract.functions.pause.return_value)

        self.assertEqual(self.client.post(f"/api/v1/tokens/{deployed.uuid}/unpause/").status_code, 200)
        deployed.refresh_from_db()
        self.assertEqual(deployed.status, ShareTokenStatus.DEPLOYED)
        self.assertEqual(chain.send_transaction.call_args.args[0], contract.functions.unpause.return_value)
        self.assertEqual(chain.send_transaction.call_count, 2)

    @patch("tokens.services.share_token_service.get_base_chain_client")
    def test_pause_failure_on_chain_keeps_the_status_and_answers_with_detail(self, chain_client):
        deployed = self.tenant.deployed_token
        failure = TokenPauseFailedException("Token pause failed: execution reverted")
        with patch("tokens.services.share_token_service.ShareTokenService._set_paused", side_effect=failure):
            response = self.client.post(f"/api/v1/tokens/{deployed.uuid}/pause/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Token pause failed: execution reverted")
        deployed.refresh_from_db()
        self.assertEqual(deployed.status, ShareTokenStatus.DEPLOYED)

    @patch("tokens.services.share_token_service.get_base_chain_client", side_effect=BaseChainConnectionError("down"))
    def test_unreachable_chain_answers_with_detail_instead_of_crashing(self, chain_client):
        response = self.client.post(f"/api/v1/tokens/{self.tenant.deployed_token.uuid}/pause/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Chain unreachable: down")

    @patch("tokens.tasks.deploy_share_token_task")
    def test_deploy_guards_leave_the_token_in_draft(self, deploy_task):
        draft = self.tenant.token

        not_active = self.client.post(f"/api/v1/tokens/{draft.uuid}/deploy/")
        self.assertEqual(not_active.status_code, 400)
        self.assertEqual(not_active.json()["detail"], "Company must be active before deploying tokens.")

        self._activate()
        Company.objects.filter(pk=self.tenant.company.pk).update(operator_wallet=None)
        Wallet.objects.filter(user_account=self.tenant.account).update(chain="bitcoin")
        no_wallet = self.client.post(f"/api/v1/tokens/{draft.uuid}/deploy/")
        self.assertEqual(no_wallet.status_code, 400)
        self.assertEqual(
            no_wallet.json()["detail"],
            "Company must have an operator wallet or verified ETH wallet before deploying tokens.",
        )

        already_deployed = self.client.post(f"/api/v1/tokens/{self.tenant.deployed_token.uuid}/deploy/")
        self.assertEqual(already_deployed.status_code, 400)
        self.assertEqual(
            already_deployed.json()["detail"],
            "Cannot deploy token with status 'Deployed'. Token must be in draft status.",
        )

        draft.refresh_from_db()
        self.assertEqual(draft.status, ShareTokenStatus.DRAFT)
        deploy_task.defer.assert_not_called()

    @patch("tokens.services.share_token_service.get_base_chain_client")
    def test_pause_and_unpause_reject_the_wrong_state(self, chain_client):
        draft, deployed = self.tenant.token, self.tenant.deployed_token
        chain_client.return_value.load_contract.return_value.functions.paused.return_value.call.return_value = False

        self.assertEqual(self.client.post(f"/api/v1/tokens/{draft.uuid}/pause/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/v1/tokens/{deployed.uuid}/unpause/").status_code, 400)
        chain_client.return_value.send_transaction.assert_not_called()

    def test_duplicate_symbol_is_rejected_by_the_unique_validator(self):
        response = self.client.post(
            "/api/v1/tokens/",
            {"name": "Again", "symbol": self.tenant.token.symbol, "tokenType": "ordinary", "totalSupply": "10"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json(), {"nonFieldErrors": ["The fields company, symbol must make a unique set."]})

    @patch("tokens.views.share_token.ShareTokenService")
    def test_issue_and_holders_shapes(self, service_class):
        token = self.tenant.deployed_token
        issuance_request = ShareIssuanceRequest.objects.create(
            token=token, recipient_address=RECIPIENT, amount=7, reason="Owner request", submitted_by=self.tenant.user
        )
        service = service_class.return_value
        service.create_issuance_request.return_value = issuance_request
        service.get_token_holders.return_value = HOLDERS

        issue = self.client.post(
            f"/api/v1/tokens/{token.uuid}/issue/",
            {"recipient": RECIPIENT, "amount": 7, "reason": "Owner request", "issuanceType": "additional"},
            format="json",
        )
        self.assertEqual(issue.status_code, 201)
        self.assertEqual(issue.json()["issuanceRequest"]["uuid"], str(issuance_request.uuid))
        service.create_issuance_request.assert_called_once_with(
            token=token,
            recipient=RECIPIENT,
            amount=7,
            user=self.tenant.user,
            reason="Owner request",
            issuance_type="additional",
        )

        holders = self.client.get(f"/api/v1/tokens/{token.uuid}/holders/")
        self.assertEqual(holders.status_code, 200)
        self.assertEqual(holders.json()["holders"], HOLDERS)
        self.assertEqual(holders.json()["totalHolders"], 1)
        service.get_token_holders.assert_called_once_with(token)

    @patch("tokens.views.share_token.ShareTokenService")
    def test_issue_rejects_a_bad_amount_with_a_field_error(self, service_class):
        token = self.tenant.deployed_token

        for amount in (None, "seven", 0):
            with self.subTest(amount=amount):
                response = self.client.post(
                    f"/api/v1/tokens/{token.uuid}/issue/",
                    {"recipient": RECIPIENT, "amount": amount, "reason": "", "issuanceType": "additional"},
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("amount", response.json())

        bad_type = self.client.post(
            f"/api/v1/tokens/{token.uuid}/issue/",
            {"recipient": RECIPIENT, "amount": 1, "issuanceType": "airdrop"},
            format="json",
        )
        self.assertEqual(bad_type.status_code, 400)
        self.assertIn("issuanceType", bad_type.json())
        service_class.return_value.create_issuance_request.assert_not_called()

    @patch("tokens.views.share_token.ShareTokenService")
    def test_detail_actions_keep_filter_params_off_the_token_lookup(self, service_class):
        token = self.tenant.deployed_token
        completed = ShareIssuance.objects.create(
            token=token, recipient_address=RECIPIENT, amount="5", status=IssuanceStatus.COMPLETED
        )
        ShareIssuance.objects.create(token=token, recipient_address=RECIPIENT, amount="3")
        service_class.return_value.get_token_holders.return_value = HOLDERS

        unfiltered = self.client.get(f"/api/v1/tokens/{token.uuid}/issuances/")
        self.assertEqual(unfiltered.status_code, 200)
        self.assertEqual(unfiltered.json()["count"], 2)

        filtered = self.client.get(f"/api/v1/tokens/{token.uuid}/issuances/", {"status": "completed"})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual([row["uuid"] for row in filtered.json()["results"]], [str(completed.uuid)])
        self.assertEqual(filtered.json()["results"][0]["status"], IssuanceStatus.COMPLETED)

        pending = self.client.get(f"/api/v1/tokens/{token.uuid}/issuances/", {"status": "pending"})
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["count"], 1)

        holders = self.client.get(f"/api/v1/tokens/{token.uuid}/holders/", {"search": "zzz", "status": "draft"})
        self.assertEqual(holders.status_code, 200)
        self.assertEqual(holders.json()["token"]["uuid"], str(token.uuid))

        self.assertEqual(self.client.get("/api/v1/tokens/", {"status": "draft"}).json()["count"], 1)
