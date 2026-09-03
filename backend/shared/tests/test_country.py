from django.test import TestCase

from shared.models import Country


class GetOrCreateForCodeTest(TestCase):
    def test_alpha_2_and_alpha_3_codes_resolve_to_the_same_names_the_reconcile_map_gave(self):
        for code, name in (
            ("US", "United States"),
            ("USA", "United States"),
            ("GB", "United Kingdom"),
            ("AU", "Australia"),
            ("AUS", "Australia"),
            ("DE", "Germany"),
            ("JP", "Japan"),
            ("BO", "Bolivia"),
            ("KR", "South Korea"),
            (" nz ", "New Zealand"),
        ):
            with self.subTest(code=code):
                country = Country.get_or_create_for_code(code)
                self.assertEqual((country.code, country.name), (code.strip().upper(), name))

    def test_unknown_code_keeps_the_code_as_its_name(self):
        country = Country.get_or_create_for_code("UK")
        self.assertEqual((country.code, country.name), ("UK", "UK"))

    def test_existing_row_is_reused_and_never_renamed(self):
        existing = Country.objects.create(code="FR", name="Custom France")
        self.assertEqual(Country.get_or_create_for_code("FR"), existing)
        self.assertEqual(Country.objects.filter(code="FR").count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.name, "Custom France")
