from datetime import date, datetime

from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from shared.utils import get_client_ip
from shared.utils.blockchain import decode_exception_to_message, decode_revert_reason
from shared.utils.datetime_utils import (
    parse_date_to_timezone_aware,
    parse_end_date_inclusive,
)

DEFAULT = "Failed to prepare the transaction."
KEY = "pR3t3nd1ngT0B3aReAlK3y"
NODE_URL = f"https://base-sepolia.g.alchemy.com/v2/{KEY}"


class DecodeRevertReasonTests(SimpleTestCase):
    def test_order_expired_selector_matches_atomic_swap_contract(self):
        self.assertEqual(decode_revert_reason("0xc56873ba"), ("OrderExpired", "Swap order has expired", {}))

    def test_insufficient_balance_params_are_decoded_into_message(self):
        address = "ab" * 20
        payload = "0xe450d38c" + "0" * 24 + address + format(5, "064x") + format(10, "064x")
        error_name, _, params = decode_revert_reason(payload)
        self.assertEqual(error_name, "ERC20InsufficientBalance")
        self.assertEqual(params, {"address": "0x" + address, "balance": 5, "needed": 10})
        self.assertEqual(
            decode_exception_to_message(Exception(f"execution reverted: {payload}")),
            "Insufficient balance: you have 5 tokens but need 10",
        )

    def test_an_exception_with_no_hex_falls_back(self):
        self.assertEqual(
            decode_exception_to_message(Exception("boom"), "Swap execution failed"), "Swap execution failed"
        )

    def test_a_selector_outside_the_closed_set_is_not_repeated_back(self):
        for label, text in (
            ("a stale selector", "0xc5487b9a"),
            ("a reverted unknown", "execution reverted: 0xdeadbeefcafebabe"),
            ("hex in the node url", "Max retries exceeded with url: https://node.test/v2/0x1234567890abcdef1234"),
            ("a long provider blob", "some provider text 0x" + "ab" * 200),
        ):
            with self.subTest(case=label):
                served = decode_exception_to_message(Exception(text), DEFAULT)

                self.assertEqual(served, DEFAULT)
                self.assertNotIn("0x", served)

    def test_the_closed_set_still_answers_with_its_own_sentence(self):
        for selector, expected in (
            ("0xdf17e316", "Account is not whitelisted"),
            ("0xc56873ba", "Swap order has expired"),
        ):
            with self.subTest(selector=selector):
                served = decode_exception_to_message(
                    Exception(f"execution reverted: {selector} at {NODE_URL}"), DEFAULT
                )

                self.assertEqual(served, expected)
                self.assertNotIn(KEY, served)


class GetClientIpTests(SimpleTestCase):
    def test_prefers_first_forwarded_address(self):
        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR=" 1.2.3.4 , 5.6.7.8", REMOTE_ADDR="9.9.9.9")
        self.assertEqual(get_client_ip(request), "1.2.3.4")

    def test_falls_back_to_remote_addr(self):
        request = RequestFactory().get("/", REMOTE_ADDR="9.9.9.9")
        self.assertEqual(get_client_ip(request), "9.9.9.9")


class DateBoundsTests(SimpleTestCase):
    def test_string_date_and_datetime_all_become_the_start_of_that_day(self):
        expected = timezone.make_aware(datetime(2026, 9, 1))
        for value in ("2026-09-01", date(2026, 9, 1), datetime(2026, 9, 1)):
            with self.subTest(value=value):
                self.assertEqual(parse_date_to_timezone_aware(value), expected)
        self.assertEqual(parse_end_date_inclusive(date(2026, 9, 1)), timezone.make_aware(datetime(2026, 9, 2)))
        self.assertIsNone(parse_date_to_timezone_aware(None))
