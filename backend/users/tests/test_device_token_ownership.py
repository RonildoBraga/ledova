from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import DeviceToken

User = get_user_model()


class DeviceTokenOwnershipTest(APITestCase):
    def setUp(self):
        self.foreign_user = self._make_user("device-foreign")
        self.foreign_token = DeviceToken.objects.create(
            user=self.foreign_user,
            push_token="ExponentPushToken[foreign-owned-token]",
            device_type=DeviceToken.DeviceType.IOS,
            is_active=False,
        )
        self.foreign_active_token = DeviceToken.objects.create(
            user=self.foreign_user,
            push_token="ExponentPushToken[foreign-active-token]",
            device_type=DeviceToken.DeviceType.ANDROID,
            is_active=True,
        )
        self.actor_cases = (
            self._make_actor_case("device-regular"),
            self._make_actor_case("device-staff", is_staff=True),
            self._make_actor_case("device-super", is_superuser=True),
        )

    def _make_user(self, label, **privileges):
        return User.objects.create_user(
            email=f"{label}@example.test",
            password="pw-12345678",
            is_active=True,
            is_email_verified=True,
            **privileges,
        )

    def _make_actor_case(self, label, **privileges):
        actor = self._make_user(label, **privileges)
        active_token = DeviceToken.objects.create(
            user=actor,
            push_token=f"ExponentPushToken[{label}-active]",
            device_type=DeviceToken.DeviceType.IOS,
            is_active=True,
        )
        inactive_token = DeviceToken.objects.create(
            user=actor,
            push_token=f"ExponentPushToken[{label}-inactive]",
            device_type=DeviceToken.DeviceType.IOS,
            is_active=False,
        )
        return actor, active_token, inactive_token

    @staticmethod
    def _response_rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    def test_foreign_registration_collision_is_generic_and_preserves_owner_for_every_role(self):
        for actor, _, _ in self.actor_cases:
            self.client.force_authenticate(actor)

            response = self.client.post(
                "/api/device-tokens/register/",
                {
                    "pushToken": self.foreign_token.push_token,
                    "deviceType": DeviceToken.DeviceType.ANDROID,
                },
                format="json",
            )

            with self.subTest(actor=actor.email):
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json(), {"detail": "Device token registration conflict."})
                self.foreign_token.refresh_from_db()
                self.assertEqual(self.foreign_token.user, self.foreign_user)
                self.assertFalse(self.foreign_token.is_active)
                self.assertEqual(self.foreign_token.device_type, DeviceToken.DeviceType.IOS)

    def test_own_token_reactivation_and_type_update_succeeds_for_every_role(self):
        for actor, _, inactive_token in self.actor_cases:
            self.client.force_authenticate(actor)

            response = self.client.post(
                "/api/device-tokens/register/",
                {
                    "pushToken": inactive_token.push_token,
                    "deviceType": DeviceToken.DeviceType.ANDROID,
                },
                format="json",
            )

            with self.subTest(actor=actor.email):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["uuid"], str(inactive_token.uuid))
                inactive_token.refresh_from_db()
                self.assertEqual(inactive_token.user, actor)
                self.assertTrue(inactive_token.is_active)
                self.assertEqual(inactive_token.device_type, DeviceToken.DeviceType.ANDROID)

    def test_new_token_creation_is_owned_by_authenticated_actor_for_every_role(self):
        for index, (actor, _, _) in enumerate(self.actor_cases):
            self.client.force_authenticate(actor)
            push_token = f"ExponentPushToken[new-device-token-{index}]"

            response = self.client.post(
                "/api/device-tokens/register/",
                {
                    "pushToken": push_token,
                    "deviceType": DeviceToken.DeviceType.IOS,
                },
                format="json",
            )

            with self.subTest(actor=actor.email):
                self.assertEqual(response.status_code, 201)
                device_token = DeviceToken.objects.get(uuid=response.json()["uuid"])
                self.assertEqual(device_token.user, actor)
                self.assertEqual(device_token.push_token, push_token)
                self.assertEqual(device_token.device_type, DeviceToken.DeviceType.IOS)
                self.assertTrue(device_token.is_active)

    def test_list_and_retrieve_are_self_scoped_for_every_role(self):
        for actor, active_token, _ in self.actor_cases:
            self.client.force_authenticate(actor)

            list_response = self.client.get("/api/device-tokens/")
            own_detail = self.client.get(f"/api/device-tokens/{active_token.uuid}/")
            foreign_detail = self.client.get(f"/api/device-tokens/{self.foreign_active_token.uuid}/")

            with self.subTest(actor=actor.email):
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(
                    {row["uuid"] for row in self._response_rows(list_response)},
                    {str(active_token.uuid)},
                )
                self.assertEqual(own_detail.status_code, 200)
                self.assertEqual(own_detail.json()["uuid"], str(active_token.uuid))
                self.assertEqual(foreign_detail.status_code, 404)

    def test_unregister_foreign_token_returns_404_and_preserves_row_for_every_role(self):
        for actor, _, _ in self.actor_cases:
            self.client.force_authenticate(actor)

            response = self.client.post(
                "/api/device-tokens/unregister/",
                {"pushToken": self.foreign_active_token.push_token},
                format="json",
            )

            with self.subTest(actor=actor.email):
                self.assertEqual(response.status_code, 404)
                self.foreign_active_token.refresh_from_db()
                self.assertEqual(self.foreign_active_token.user, self.foreign_user)
                self.assertTrue(self.foreign_active_token.is_active)
                self.assertEqual(self.foreign_active_token.device_type, DeviceToken.DeviceType.ANDROID)

    def test_owner_unregister_releases_token_for_new_owner_for_every_role(self):
        for index, (new_owner, _, _) in enumerate(self.actor_cases):
            old_owner = self._make_user(f"device-switch-old-{index}")
            push_token = f"ExponentPushToken[device-switch-{index}]"
            old_token = DeviceToken.objects.create(
                user=old_owner,
                push_token=push_token,
                device_type=DeviceToken.DeviceType.IOS,
                is_active=True,
            )
            self.client.force_authenticate(old_owner)

            unregister_response = self.client.post(
                "/api/device-tokens/unregister/",
                {"pushToken": push_token},
                format="json",
            )

            with self.subTest(new_owner=new_owner.email, operation="release"):
                self.assertEqual(unregister_response.status_code, 204)
                self.assertFalse(DeviceToken.objects.filter(uuid=old_token.uuid).exists())
                self.assertFalse(DeviceToken.objects.filter(push_token=push_token).exists())

            self.client.force_authenticate(new_owner)
            register_response = self.client.post(
                "/api/device-tokens/register/",
                {
                    "pushToken": push_token,
                    "deviceType": DeviceToken.DeviceType.ANDROID,
                },
                format="json",
            )

            with self.subTest(new_owner=new_owner.email, operation="register"):
                self.assertEqual(register_response.status_code, 201)
                new_token = DeviceToken.objects.get(uuid=register_response.json()["uuid"])
                self.assertNotEqual(new_token.uuid, old_token.uuid)
                self.assertEqual(new_token.user, new_owner)
                self.assertEqual(new_token.push_token, push_token)
                self.assertEqual(new_token.device_type, DeviceToken.DeviceType.ANDROID)
                self.assertTrue(new_token.is_active)

    def test_anonymous_requests_are_rejected(self):
        self.client.force_authenticate(user=None)

        list_response = self.client.get("/api/device-tokens/")
        register_response = self.client.post(
            "/api/device-tokens/register/",
            {
                "pushToken": "ExponentPushToken[anonymous-register]",
                "deviceType": DeviceToken.DeviceType.IOS,
            },
            format="json",
        )
        unregister_response = self.client.post(
            "/api/device-tokens/unregister/",
            {"pushToken": self.foreign_active_token.push_token},
            format="json",
        )

        self.assertEqual(list_response.status_code, 401)
        self.assertEqual(register_response.status_code, 401)
        self.assertEqual(unregister_response.status_code, 401)
