from django.contrib.auth import get_user_model
from django.test import TestCase

from companies.models import Company, CompanyStatus, CompanyType
from companies.serializers import CompanyDetailSerializer
from users.models import UserProfile

User = get_user_model()


class CompanyPrimaryContactTest(TestCase):
    def test_primary_contact_is_the_owner_profile(self):
        owner = User.objects.create_user(email="owner@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=owner, full_name="Owner Person")
        company = Company.objects.create(
            owner=owner,
            name="Contact Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="000000777",
            status=CompanyStatus.ACTIVE,
        )

        self.assertEqual(company.primary_contact, profile)
        self.assertEqual(CompanyDetailSerializer(company).data["primary_contact"]["full_name"], "Owner Person")
