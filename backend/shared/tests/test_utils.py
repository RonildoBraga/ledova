from django.test import RequestFactory, SimpleTestCase

from shared.utils import get_client_ip
from shared.utils.blockchain import decode_exception_to_message, decode_revert_reason


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
        stale_selector = "0xc5487b9a"  # the pre-fix table mislabelled this as SwapExpired
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
