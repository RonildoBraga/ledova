from unittest.mock import Mock, patch

from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant

ADDRESS = "0x" + "a" * 40


class WhitelistStatusViewTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("wlstatus")
        self.client.force_authenticate(self.tenant.user)
        self.url = f"/api/v1/trading/whitelist/{ADDRESS}/status/"

    def _service(self, **attrs):
        service = Mock()
        service.chain_client.to_checksum_address.return_value = ADDRESS
        for name, value in attrs.items():
            setattr(service, name, value)
        return service

    def test_a_whitelisted_address_reports_the_whitelisted_state(self):
        service = self._service(
            get_investor_info=Mock(return_value={"whitelisted": True}),
            can_receive=Mock(return_value=True),
        )
        with patch("whitelist.views.status.WhitelistService", return_value=service):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "whitelisted")
        self.assertTrue(response.json()["isWhitelisted"])

    def test_an_address_the_chain_says_is_absent_reports_not_whitelisted(self):
        service = self._service(
            get_investor_info=Mock(return_value={"whitelisted": False}),
            can_receive=Mock(return_value=False),
        )
        with patch("whitelist.views.status.WhitelistService", return_value=service):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_whitelisted")
        self.assertFalse(response.json()["isWhitelisted"])

    def test_a_chain_error_is_reported_as_unknown_rather_than_a_refusal(self):
        service = self._service(get_investor_info=Mock(side_effect=RuntimeError("rpc down")))
        with patch("whitelist.views.status.WhitelistService", return_value=service):
            response = self.client.get(self.url)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "unknown")
        self.assertFalse(body["isWhitelisted"])
        self.assertFalse(body["canReceive"])
