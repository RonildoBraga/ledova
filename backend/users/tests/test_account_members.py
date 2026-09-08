from django.contrib.auth import get_user_model
from django.test import TestCase

from shared.tests.tenants import make_tenant
from users.models import UserProfile
from users.services import account_members


class AccountMembersReturnsTheAccountAndNothingElseTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.one = make_tenant("membersone")
        cls.two = make_tenant("memberstwo")
        cls.second = get_user_model().objects.create_user(
            email="second@members.example.test", password="pw-12345678", is_active=True, is_email_verified=True
        )
        cls.one.account.user_profiles.add(UserProfile.objects.create(user=cls.second, full_name="second member"))

    def test_it_returns_every_member_of_the_account(self):
        self.assertEqual(
            sorted(user.email for user in account_members(self.one.account)),
            sorted([self.one.user.email, self.second.email]),
        )

    def test_it_returns_nobody_from_another_account(self):
        self.assertNotIn(self.two.user, account_members(self.one.account))

    def test_it_filters_itself_rather_than_trusting_the_connection(self):
        self.assertEqual([user.email for user in account_members(self.two.account)], [self.two.user.email])

    def test_an_account_with_no_members_returns_nothing(self):
        self.one.account.user_profiles.clear()

        self.assertEqual(account_members(self.one.account), [])
