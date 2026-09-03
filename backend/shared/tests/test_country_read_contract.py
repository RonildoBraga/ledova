from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from shared.models import Country

User = get_user_model()


class CountryReadContractTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="country-reader@example.test",
            password="pw-12345678",
        )
        self.staff = User.objects.create_user(
            email="country-staff@example.test",
            password="pw-12345678",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="country-superuser@example.test", password="pw-12345678")
        self.available = Country.objects.create(
            name="Available Country",
            code="AAC",
            is_available=True,
        )
        self.unavailable = Country.objects.create(
            name="Unavailable Country",
            code="UAC",
            is_available=False,
        )

    @staticmethod
    def rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    def test_only_available_countries_are_visible_to_every_authenticated_role(self):
        for actor in (self.user, self.staff, self.superuser):
            self.client.force_authenticate(actor)

            list_response = self.client.get("/api/countries/")
            available_response = self.client.get(f"/api/countries/{self.available.uuid}/")
            unavailable_response = self.client.get(f"/api/countries/{self.unavailable.uuid}/")

            with self.subTest(actor=actor.email):
                self.assertEqual(list_response.status_code, 200)
                returned = {row["uuid"] for row in self.rows(list_response)}
                self.assertIn(str(self.available.uuid), returned)
                self.assertNotIn(str(self.unavailable.uuid), returned)
                self.assertEqual(available_response.status_code, 200)
                self.assertEqual(unavailable_response.status_code, 404)

    def test_rows_carry_the_keys_the_shared_types_declare(self):
        self.client.force_authenticate(self.user)
        row = self.client.get(f"/api/countries/{self.available.uuid}/").json()
        self.assertEqual(
            row,
            {
                "uuid": str(self.available.uuid),
                "name": "Available Country",
                "code": "AAC",
                "dialCode": None,
                "isAvailable": True,
            },
        )
