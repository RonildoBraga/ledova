from django.test import TestCase

from tokens.models import CapitalIncreaseRequest


class DilutionArithmeticTest(TestCase):
    def _request(self, additional_shares):
        return CapitalIncreaseRequest(additional_shares=additional_shares)

    def test_a_first_issuance_dilutes_nobody(self):
        self.assertEqual(self._request(100).dilution_against(0), 0.0)

    def test_the_share_is_measured_against_the_supply_after_the_increase(self):
        self.assertEqual(self._request(100).dilution_against(900), 10.0)

    def test_it_rounds_to_two_places(self):
        self.assertEqual(self._request(1).dilution_against(300), 0.33)

    def test_it_reaches_the_database_not_at_all(self):
        request = self._request(100)

        with self.assertNumQueries(0):
            request.dilution_against(900)
