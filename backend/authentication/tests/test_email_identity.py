from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import F, Value
from django.db.models.functions import Trim
from django.test import SimpleTestCase, TestCase
from rest_framework import serializers

from authentication.email import (
    EMAIL_ERROR,
    EmailDestinationKey,
    EmailError,
    email_destination_expression,
    normalize_email,
)
from authentication.serializers.fields import NormalizedEmailField

User = get_user_model()


class EmailSerializer(serializers.Serializer):
    email = NormalizedEmailField(required=True)


class EmailNormalizerTests(SimpleTestCase):
    def test_normalizes_outer_u0020_and_full_ascii_case(self):
        self.assertEqual(
            normalize_email(" Owner.Name+Tag@EXAMPLE.TEST "),
            "owner.name+tag@example.test",
        )

    def test_preserves_provider_specific_structure(self):
        self.assertEqual(
            normalize_email("First.Last+Tag@Example.COM"),
            "first.last+tag@example.com",
        )

    def test_is_idempotent(self):
        normalized = normalize_email(" Owner@EXAMPLE.COM ")
        self.assertEqual(normalize_email(normalized), normalized)

    def test_accepts_exactly_254_ascii_characters(self):
        address = f"{'a' * 64}@{'b' * 63}.{'c' * 63}.{'d' * 61}"
        self.assertEqual(len(address), 254)
        self.assertEqual(normalize_email(address), address)

    def test_rejects_more_than_254_raw_characters_before_trimming(self):
        address = f" {'a' * 64}@{'b' * 63}.{'c' * 63}.{'d' * 60} "
        self.assertEqual(len(address), 255)
        with self.assertRaises(EmailError):
            normalize_email(address)

    def test_rejects_non_string_empty_and_space_only_values(self):
        for value in (None, 1, True, "", "   "):
            with self.subTest(value=value), self.assertRaises(EmailError):
                normalize_email(value)

    def test_rejects_nonprintable_ascii_before_normalization(self):
        for character in ("\x00", "\t", "\n", "\r", "\x1f", "\x7f"):
            with self.subTest(character=repr(character)), self.assertRaises(EmailError):
                normalize_email(f"owner@example.com{character}")

    def test_rejects_non_ascii_forms(self):
        for address in (
            "owner@example.com\u00a0",
            "ownér@example.com",
            "owner@éxample.com",
            "owner@bücher.example",
        ):
            with self.subTest(address=address), self.assertRaises(EmailError):
                normalize_email(address)

    def test_rejects_invalid_printable_ascii_syntax(self):
        for address in ("not-an-email", "owner@", "@example.com", "owner@example"):
            with self.subTest(address=address), self.assertRaises(EmailError):
                normalize_email(address)

    def test_errors_are_fixed_and_do_not_contain_the_input(self):
        private_value = "private-value"
        with self.assertRaises(EmailError) as raised:
            normalize_email(private_value)
        self.assertEqual(str(raised.exception), EMAIL_ERROR)
        self.assertNotIn(private_value, str(raised.exception))

    def test_destination_expression_uses_lower_trim_and_c_collation(self):
        expression = email_destination_expression()
        self.assertIsInstance(expression, EmailDestinationKey)
        trim = expression.source_expressions[0]
        self.assertIsInstance(trim, Trim)
        self.assertEqual(trim.source_expressions, [F("email")])


class EmailSerializerTests(SimpleTestCase):
    def test_field_applies_canonicalization(self):
        serializer = EmailSerializer(data={"email": " Owner.Name+Tag@EXAMPLE.TEST "})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["email"], "owner.name+tag@example.test")

    def test_field_rejects_disallowed_raw_input(self):
        invalid_values = (
            "owner@example.com\t",
            "owner@example.com\n",
            "owner@example.com\u00a0",
            "ownér@example.com",
            f"{'a' * 255}@example.com",
            123,
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                serializer = EmailSerializer(data={"email": value})
                self.assertFalse(serializer.is_valid())
                self.assertEqual(serializer.errors["email"], ["Enter a valid email address."])
                self.assertNotIn(str(value), str(serializer.errors))

    def test_field_has_the_v2_limit_and_raw_whitespace_contract(self):
        field = EmailSerializer().fields["email"]
        self.assertEqual(field.max_length, 254)
        self.assertFalse(field.trim_whitespace)


class EmailDestinationExpressionTests(TestCase):
    def test_expression_executes_canonical_comparison(self):
        user = User.objects.create(email="legacy.owner@example.test")
        destination_key = (
            User.objects.filter(pk=user.pk)
            .annotate(destination_key=EmailDestinationKey(Value(" Legacy.Owner@EXAMPLE.TEST ")))
            .values_list("destination_key", flat=True)
            .get()
        )
        self.assertEqual(destination_key, "legacy.owner@example.test")

    def test_expression_uses_c_collation_only_on_postgresql(self):
        query = User.objects.annotate(destination_key=email_destination_expression()).filter(
            destination_key="owner@example.test"
        )
        sql = str(query.query)
        self.assertIn("LOWER(TRIM(", sql)
        if connection.vendor == "postgresql":
            self.assertIn('COLLATE "C"', sql)
        else:
            self.assertNotIn("COLLATE", sql)
