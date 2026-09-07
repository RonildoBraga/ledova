from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant
from whitelist.constants import (
    WHITELIST_STATUS_NOT_WHITELISTED,
    WHITELIST_STATUS_UNKNOWN,
    WHITELIST_STATUS_WHITELISTED,
)
from whitelist.services import WhitelistService

ADDRESS = "0x" + "a" * 40


class WhitelistInvestorStatusServiceTest(TestCase):
    def _service(self, **attrs):
        service = WhitelistService.__new__(WhitelistService)
        service.chain_client = Mock()
        service.chain_client.to_checksum_address.side_effect = lambda address: address
        service.contract_address = "0x" + "d" * 40
        service._contract = Mock()
        for name, value in attrs.items():
            setattr(service, name, value)
        return service

    def test_a_whitelisted_address_reports_the_whitelisted_state(self):
        service = self._service(
            get_investor_info=Mock(return_value={"whitelisted": True}),
            can_receive=Mock(return_value=True),
        )

        self.assertEqual(
            service.investor_status(ADDRESS),
            {
                "address": ADDRESS,
                "is_whitelisted": True,
                "can_receive": True,
                "status": WHITELIST_STATUS_WHITELISTED,
            },
        )

    def test_an_address_the_chain_says_is_absent_reports_not_whitelisted(self):
        service = self._service(
            get_investor_info=Mock(return_value={"whitelisted": False}),
            can_receive=Mock(return_value=False),
        )

        self.assertEqual(service.investor_status(ADDRESS)["status"], WHITELIST_STATUS_NOT_WHITELISTED)

    def test_a_chain_error_is_reported_as_unknown_rather_than_a_refusal(self):
        service = self._service(get_investor_info=Mock(side_effect=RuntimeError("rpc down")))

        self.assertEqual(
            service.investor_status(ADDRESS),
            {
                "address": ADDRESS,
                "is_whitelisted": False,
                "can_receive": False,
                "status": WHITELIST_STATUS_UNKNOWN,
            },
        )

    def test_the_unknown_answer_reports_the_address_as_given_because_checksumming_is_what_failed(self):
        service = self._service(get_investor_info=Mock(side_effect=RuntimeError("rpc down")))
        service.chain_client.to_checksum_address.side_effect = ValueError("not an address")

        self.assertEqual(service.investor_status("nonsense")["address"], "nonsense")

    def test_a_failure_in_can_receive_alone_still_answers_unknown(self):
        service = self._service(
            get_investor_info=Mock(return_value={"whitelisted": True}),
            can_receive=Mock(side_effect=RuntimeError("rpc down")),
        )

        self.assertEqual(service.investor_status(ADDRESS)["status"], WHITELIST_STATUS_UNKNOWN)


class WhitelistStatusViewTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("wlstatus")
        self.client.force_authenticate(self.tenant.user)
        self.url = f"/api/v1/trading/whitelist/{ADDRESS}/status/"

    def _view_over(self, payload):
        service = Mock()
        service.investor_status.return_value = payload
        return patch("whitelist.views.status.WhitelistService", return_value=service), service

    def test_the_view_renders_what_the_service_answers(self):
        patcher, service = self._view_over(
            {
                "address": ADDRESS,
                "is_whitelisted": True,
                "can_receive": True,
                "status": WHITELIST_STATUS_WHITELISTED,
            }
        )
        with patcher:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"address": ADDRESS, "isWhitelisted": True, "canReceive": True, "status": WHITELIST_STATUS_WHITELISTED},
        )
        service.investor_status.assert_called_once_with(ADDRESS)

    def test_an_unknown_answer_is_still_a_200(self):
        patcher, _ = self._view_over(
            {
                "address": ADDRESS,
                "is_whitelisted": False,
                "can_receive": False,
                "status": WHITELIST_STATUS_UNKNOWN,
            }
        )
        with patcher:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], WHITELIST_STATUS_UNKNOWN)

    def test_an_anonymous_caller_is_refused(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, 401)
