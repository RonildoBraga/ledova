from unittest.mock import patch

from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus
from shared.tests.tenants import make_tenant

BASE = "/api/v1/offerings/"
PAYLOAD = {
    "exemption": "s708_11_professional",
    "pricePerShare": "3.00",
    "minimumShares": 5,
    "targetShares": 40,
    "capShares": 80,
    "opensAt": "2027-03-01T00:00:00Z",
    "summary": "Second tranche",
    "useOfProceeds": "Plant",
}
PROMISED_BY_THE_CLIENT_TYPE = {"uuid", "status", "statusDisplay", "canBeEdited", "canBeDeleted", "tokenUuid"}


class AMutationAnswersWithTheShapeTheTypePromisesTest(APITestCase):

    def setUp(self):
        patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.client.force_authenticate(self.tenant.user)

    def test_creating_an_offering_answers_with_the_offering(self):
        response = self.client.post(BASE, {"token": str(self.tenant.token.uuid), **PAYLOAD}, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(PROMISED_BY_THE_CLIENT_TYPE - set(response.json()), set())

    def test_the_created_offering_can_be_addressed_by_what_it_answered(self):
        created = self.client.post(BASE, {"token": str(self.tenant.token.uuid), **PAYLOAD}, format="json")

        fetched = self.client.get(f"{BASE}{created.json()['uuid']}/")

        self.assertEqual(fetched.status_code, 200, fetched.content)

    def test_editing_an_offering_answers_with_the_offering(self):
        response = self.client.patch(f"{BASE}{self.tenant.offering.uuid}/", {"summary": "Changed"}, format="json")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(PROMISED_BY_THE_CLIENT_TYPE - set(response.json()), set())

    def test_all_three_mutations_answer_in_the_same_shape_as_the_read(self):
        created = self.client.post(BASE, {"token": str(self.tenant.token.uuid), **PAYLOAD}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        detail = f"{BASE}{created.json()['uuid']}/"
        read = self.client.get(detail)

        self.assertEqual(set(created.json()), set(read.json()))
        for method in (self.client.put, self.client.patch):
            with self.subTest(method=method.__name__):
                response = method(detail, {"token": str(self.tenant.token.uuid), **PAYLOAD}, format="json")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(set(response.json()), set(self.client.get(detail).json()))
