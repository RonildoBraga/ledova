from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

User = get_user_model()


class EmailConstraintTest(TestCase):
    constraint_names = {
        "auth_user_email_v2_ascii_ck",
        "auth_user_email_v2_canon_ck",
        "auth_user_email_v2_key_uniq",
    }

    def assert_email_rejected(self, email):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(email=email, password="!")

    def test_canonical_email_and_length_boundary_are_accepted(self):
        longest = f"{'a' * 64}@{'b' * 63}.{'c' * 63}.{'d' * 61}"
        self.assertEqual(len(longest), 254)

        canonical = User.objects.create(email="owner@example.test", password="!")
        boundary = User.objects.create(email=longest, password="!")

        self.assertEqual(canonical.email, "owner@example.test")
        self.assertEqual(boundary.email, longest)

    def test_noncanonical_and_out_of_range_values_are_rejected(self):
        too_long = f"{'a' * 64}@{'b' * 63}.{'c' * 63}.{'d' * 62}"
        rejected = [
            " Owner@example.test",
            "owner@example.test ",
            "OWNER@example.test",
            "owner\texample.test",
            "owner\n@example.test",
            "owner\x1f@example.test",
            "owner\x7f@example.test",
            "owner\u00a0@example.test",
            "own\u00e9r@example.test",
            "",
        ]
        if connection.vendor == "sqlite":
            rejected.extend(["owner\x00@example.test", too_long])

        for email in rejected:
            with self.subTest(value=ascii(email)):
                self.assert_email_rejected(email)

    def test_failed_update_preserves_the_canonical_address(self):
        user = User.objects.create(email="owner@example.test", password="!")

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(email=" Owner@EXAMPLE.TEST ")

        user.refresh_from_db()
        self.assertEqual(user.email, "owner@example.test")

    def test_constraint_names_and_kinds_are_introspectable(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, User._meta.db_table)

        self.assertTrue(self.constraint_names.issubset(constraints))
        self.assertTrue(constraints["auth_user_email_v2_ascii_ck"]["check"])
        self.assertTrue(constraints["auth_user_email_v2_canon_ck"]["check"])
        self.assertTrue(constraints["auth_user_email_v2_key_uniq"]["unique"])

    def test_backend_schema_definitions_pin_byte_and_collation_semantics(self):
        table = User._meta.db_table
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                cursor.execute(
                    """
                    SELECT conname, pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE conrelid = %s::regclass
                      AND conname IN (%s, %s)
                    """,
                    [
                        table,
                        "auth_user_email_v2_ascii_ck",
                        "auth_user_email_v2_canon_ck",
                    ],
                )
                definitions = dict(cursor.fetchall())
                cursor.execute(
                    """
                    SELECT pg_get_indexdef(indexrelid)
                    FROM pg_index
                    JOIN pg_class ON pg_class.oid = indexrelid
                    WHERE indrelid = %s::regclass
                      AND pg_class.relname = %s
                    """,
                    [table, "auth_user_email_v2_key_uniq"],
                )
                definitions["auth_user_email_v2_key_uniq"] = cursor.fetchone()[0]
                for name in self.constraint_names:
                    self.assertIn('COLLATE "C"', definitions[name])
                self.assertIn("[^ -~]", definitions["auth_user_email_v2_ascii_ck"])
                ascii_definition = definitions["auth_user_email_v2_ascii_ck"].upper()
                self.assertIn("CHAR_LENGTH", ascii_definition)
                self.assertIn("254", ascii_definition)
            else:
                cursor.execute(
                    """
                    SELECT sql
                    FROM sqlite_master
                    WHERE (type = 'table' AND name = %s)
                       OR (type = 'index' AND name = %s)
                    """,
                    [table, "auth_user_email_v2_key_uniq"],
                )
                definition = " ".join(row[0] for row in cursor.fetchall()).upper()
                self.assertIn("CAST", definition)
                self.assertIn("GLOB", definition)
                self.assertIn("LOWER(TRIM", definition)
