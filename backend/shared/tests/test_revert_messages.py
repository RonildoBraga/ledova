from django.test import SimpleTestCase
from web3.exceptions import ContractCustomError

from integrations.base_chain.exceptions import GasEstimationError
from shared.tests.reverts import (
    RPC_HOST,
    RPC_KEY,
    RPC_URL,
    actionable_reverts,
    provider_revert,
    revert_payload,
)
from shared.utils.blockchain import decode_exception_to_message, decode_revert_reason

DEFAULT = "Transfer preparation failed."


class RevertMessagesTest(SimpleTestCase):
    def assert_safe_message(self, error, expected):
        actual = decode_exception_to_message(error, DEFAULT)
        self.assertEqual(actual, expected)
        for secret in (RPC_HOST, RPC_KEY, "0x"):
            self.assertNotIn(secret, actual)

    def test_each_actionable_error_comes_from_a_real_abi_selector_and_not_the_longer_url(self):
        for payload, expected in actionable_reverts():
            with self.subTest(expected=expected):
                self.assert_safe_message(provider_revert(payload), expected)
                self.assert_safe_message(ValueError(f"execution reverted: {payload} at {RPC_URL}"), expected)
                self.assert_safe_message(ContractCustomError("execution reverted", data=payload), expected)

    def test_a_sanitized_outer_error_still_uses_its_preserved_rpc_cause(self):
        for payload, expected in actionable_reverts():
            with self.subTest(expected=expected):
                wrapper = GasEstimationError("The node would not estimate gas.")
                wrapper.__cause__ = provider_revert(payload)
                self.assert_safe_message(wrapper, expected)

    def test_unknown_payloads_and_hex_in_urls_never_echo_or_guess_a_reason(self):
        for value in (
            "execution reverted: 0xdeadbeef",
            f"connection failed at {RPC_URL}",
            "https://node.example.test/v2/reverted:0xdf17e316",
            "https://node.example.test/v2/0xdf17e316",
            "execution reverted: 0x" + "ab" * 5000,
            "0xnothexadecimal",
        ):
            with self.subTest(value=value[:60]):
                self.assert_safe_message(ValueError(value), DEFAULT)
        self.assertEqual(decode_revert_reason("0xdeadbeef"), (None, None, {}))

    def test_structured_arguments_complete_a_selector_only_message_for_the_same_reason(self):
        for payload, expected in actionable_reverts():
            self.assert_safe_message(ContractCustomError(f"execution reverted: {payload[:10]}", data=payload), expected)

    def test_a_truncated_allowance_payload_does_not_invent_zero_amounts(self):
        self.assert_safe_message(
            ValueError(revert_payload("ERC20InsufficientAllowance(address,uint256,uint256)")),
            "Insufficient token allowance",
        )

    def test_conflicting_reasons_fall_back_instead_of_choosing_one(self):
        self.assert_safe_message(
            ValueError(
                {"data": revert_payload("OrderExpired()"), "originalError": {"data": revert_payload("EnforcedPause()")}}
            ),
            DEFAULT,
        )

    def test_cyclic_error_data_and_causes_terminate_without_repeating_input(self):
        payload = {"data": "0xdeadbeef"}
        payload["originalError"] = payload
        error = ValueError(payload)
        error.__cause__ = error
        self.assert_safe_message(error, DEFAULT)

    def test_the_existing_swap_fallback_can_still_decode_a_nested_rpc_error(self):
        error = RuntimeError({"error": {"data": {"return": revert_payload("OrderExpired()")}}})
        self.assertEqual(decode_exception_to_message(error, "Swap execution failed"), "Swap order has expired")
