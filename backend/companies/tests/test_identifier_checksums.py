from math import gcd

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus, CompanyType
from companies.validators import (
    ACN_WEIGHTS,
    abn_carries_acn,
    acn_is_valid,
    checked_abn,
    checked_acn,
    validate_abn,
    validate_acn,
)

ASIC_WORKED_EXAMPLE = "004 085 616"
ABR_WORKED_EXAMPLE = "83 914 571 673"
COMPANY_ACN = "100000682"
COMPANY_ABN = "10100000682"
User = get_user_model()


def one_digit_changed(number: str):
    digits = number.replace(" ", "")
    for index, digit in enumerate(digits):
        for replacement in "0123456789":
            if replacement != digit:
                yield index, digits[:index] + replacement + digits[index + 1 :]


def accepted(validator, candidate) -> bool:
    try:
        validator(candidate)
    except ValidationError:
        return False
    return True


class ThePublishedWorkedExamplesPassTest(TestCase):

    def test_the_acn_from_the_asic_documentation_is_accepted(self):
        validate_acn(ASIC_WORKED_EXAMPLE)

    def test_the_abn_from_the_abr_documentation_is_accepted(self):
        validate_abn(ABR_WORKED_EXAMPLE)

    def test_the_acn_check_catches_every_change_at_a_position_its_weight_can_see(self):
        for index, candidate in one_digit_changed(ASIC_WORKED_EXAMPLE):
            if index < len(ACN_WEIGHTS) and gcd(ACN_WEIGHTS[index], 10) > 1:
                continue
            with self.subTest(candidate=candidate):
                self.assertFalse(accepted(validate_acn, candidate))

    def test_the_acn_check_misses_only_what_a_modulus_of_ten_cannot_see(self):
        missed = [
            index for index, candidate in one_digit_changed(ASIC_WORKED_EXAMPLE) if accepted(validate_acn, candidate)
        ]

        self.assertNotEqual(missed, [])
        self.assertTrue(all(gcd(ACN_WEIGHTS[index], 10) > 1 for index in missed), missed)

    def test_the_abn_check_catches_every_single_digit_change(self):
        for _, candidate in one_digit_changed(ABR_WORKED_EXAMPLE):
            with self.subTest(candidate=candidate):
                self.assertFalse(accepted(validate_abn, candidate))

    def test_the_published_abn_does_not_carry_a_company_acn(self):
        self.assertFalse(acn_is_valid(ABR_WORKED_EXAMPLE.replace(" ", "")[2:]))

    def test_length_is_still_checked_before_the_checksum(self):
        self.assertRaises(ValidationError, validate_acn, "00408561")
        self.assertRaises(ValidationError, validate_abn, "8391457167")
        self.assertRaises(ValidationError, validate_acn, "00408561x")


class TheSerializerAndTheModelAgreeTest(TestCase):

    def test_the_serializer_helper_normalises_what_it_accepts(self):
        self.assertEqual(checked_acn(ASIC_WORKED_EXAMPLE), "004085616")
        self.assertEqual(checked_abn(ABR_WORKED_EXAMPLE), "83914571673")

    def test_an_empty_abn_stays_legal(self):
        self.assertEqual(checked_abn(""), "")
        Company(owner=None, acn=COMPANY_ACN, abn="").clean()

    def test_the_serializer_helper_refuses_what_the_validator_refuses(self):
        self.assertRaises(DRFValidationError, checked_acn, "004085617")
        self.assertRaises(DRFValidationError, checked_abn, "83914571674")

    def test_an_abn_that_does_not_carry_the_acn_is_refused_by_the_model(self):
        company = Company(owner=None, acn=COMPANY_ACN, abn=ABR_WORKED_EXAMPLE.replace(" ", ""))

        with self.assertRaises(ValidationError) as refusal:
            company.clean()

        self.assertIn("abn", refusal.exception.error_dict)

    def test_the_matching_pair_passes(self):
        self.assertTrue(abn_carries_acn(COMPANY_ABN, COMPANY_ACN))
        Company(owner=None, acn=COMPANY_ACN, abn=COMPANY_ABN).clean()


class TheRegistrationApiChecksTheDigitsTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="checksum@example.test", password="pw-12345678")
        self.client.force_authenticate(self.user)

    def payload(self, **overrides):
        return {
            "name": "Checksum Pty Ltd",
            "companyType": CompanyType.PROPRIETARY,
            "acn": COMPANY_ACN,
            "primaryContact": {"firstName": "Ada", "lastName": "Lovelace"},
            **overrides,
        }

    def register(self, **overrides):
        return self.client.post("/api/v1/companies/", self.payload(**overrides), format="json")

    def test_a_company_with_a_valid_acn_registers(self):
        response = self.register()

        self.assertEqual(response.status_code, 201, response.content)

    def test_a_company_whose_acn_fails_the_check_is_refused(self):
        response = self.register(acn="100000683")

        self.assertEqual(response.status_code, 400)
        self.assertIn("acn", response.json())
        self.assertFalse(Company.objects.filter(name="Checksum Pty Ltd").exists())

    def test_a_company_whose_abn_does_not_carry_its_acn_is_refused(self):
        response = self.register(abn=ABR_WORKED_EXAMPLE.replace(" ", ""))

        self.assertEqual(response.status_code, 400)
        self.assertIn("abn", response.json())

    def test_the_admin_change_form_refuses_an_acn_that_fails_the_check(self):
        owner = User.objects.create_user(email="checksum-owner@example.test", password="pw-12345678")
        company = Company.objects.create(
            owner=owner,
            name="Draft Checksum Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn=COMPANY_ACN,
            status=CompanyStatus.DRAFT,
        )
        company.acn = "100000683"

        with self.assertRaises(ValidationError) as refusal:
            company.full_clean()

        self.assertIn("acn", refusal.exception.error_dict)
