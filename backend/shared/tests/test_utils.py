from datetime import date, datetime

from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from shared.utils import get_client_ip
from shared.utils.blockchain import decode_exception_to_message, decode_revert_reason
from shared.utils.datetime_utils import (
    parse_date_to_timezone_aware,
    parse_end_date_inclusive,
)


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

    def test_unknown_selector_and_no_hex_fall_back(self):
        stale_selector = "0xc5487b9a"
        self.assertEqual(
            decode_exception_to_message(Exception(stale_selector)), f"Unknown error (selector: {stale_selector})"
        )
        self.assertEqual(
            decode_exception_to_message(Exception("boom"), "Swap execution failed"), "Swap execution failed"
        )


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
