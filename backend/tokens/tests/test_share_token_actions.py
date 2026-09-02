"""The share-token transitions and response keys the dashboard drives for the owner's own token."""

from unittest.mock import patch

from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus
from shared.tests.tenants import make_tenant
from tokens.models import ShareIssuanceRequest, ShareTokenStatus

RECIPIENT = "0x" + "9" * 40
HOLDERS = [{"address": RECIPIENT, "name": None, "balance": "5", "source": "issuances", "percentage": 100.0}]
ELIGIBILITY = {
    "can_receive": True,
    "db_whitelisted": True,
    "on_chain_whitelisted": False,
    "investor_type": "retail",
    "investor_type_display": "Retail",
}


class ShareTokenActionTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("owner")
        self.client.force_authenticate(self.tenant.user)

    @patch("tokens.views.share_token.deploy_share_token_task")
    def test_deploy_pause_and_unpause_move_status(self, deploy_task):
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        draft, deployed = self.tenant.token, self.tenant.deployed_token

        self.assertEqual(self.client.post(f"/api/v1/tokens/{draft.uuid}/deploy/").status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.status, ShareTokenStatus.DEPLOYING)
        deploy_task.defer.assert_called_once_with(token_uuid=str(draft.uuid))

        self.assertEqual(self.client.post(f"/api/v1/tokens/{deployed.uuid}/pause/").status_code, 200)
        deployed.refresh_from_db()
        self.assertEqual(deployed.status, ShareTokenStatus.PAUSED)

        self.assertEqual(self.client.post(f"/api/v1/tokens/{deployed.uuid}/unpause/").status_code, 200)
        deployed.refresh_from_db()
        self.assertEqual(deployed.status, ShareTokenStatus.DEPLOYED)

    @patch("tokens.views.share_token.WhitelistService")
    @patch("tokens.views.share_token.ShareTokenService")
    def test_issue_holders_and_can_receive_shapes(self, service_class, whitelist_class):
        token = self.tenant.deployed_token
        issuance_request = ShareIssuanceRequest.objects.create(
            token=token, recipient_address=RECIPIENT, amount=7, reason="Owner request", submitted_by=self.tenant.user
        )
        service = service_class.return_value
        service.create_issuance_request.return_value = issuance_request
        service.get_token_holders.return_value = HOLDERS
        whitelist = whitelist_class.return_value
        whitelist.get_receive_eligibility.return_value = ELIGIBILITY

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
        service.get_token_holders.assert_called_once_with(token)

        can_receive = self.client.get(f"/api/v1/tokens/{token.uuid}/can-receive/{RECIPIENT}/")
        self.assertEqual(can_receive.status_code, 200)
        self.assertTrue(can_receive.json()["canReceive"])
        whitelist.get_receive_eligibility.assert_called_once_with(RECIPIENT)
