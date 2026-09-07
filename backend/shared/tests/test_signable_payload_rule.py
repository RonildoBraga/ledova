from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from eth_account import Account

from shared.tests.signable import (
    JAVASCRIPT_SAFE_INTEGER,
    assert_signable,
    unsafe_numbers,
)
from shared.tests.tenants import make_tenant
from tokens.models import SwapOrder
from tokens.services import AtomicSwapService
from tokens.services.signing_challenge import (
    CHALLENGE_TYPES,
    challenge_response,
    issue_challenge,
)

SIGNER = Account.from_key("0x" + "5c" * 32)
CONTRACT = "0x" + "7b" * 20
OVER_THE_LIMIT = JAVASCRIPT_SAFE_INTEGER + 1


def stressed(field: dict):
    if field["type"].startswith("uint"):
        return OVER_THE_LIMIT
    if field["type"] == "address":
        return SIGNER.address
    return "stress"


class EverySignablePayloadSurvivesJsonParseTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("signable-rule")

    def test_every_challenge_purpose_survives_a_value_above_the_safe_range(self):
        for purpose, types in CHALLENGE_TYPES.items():
            with self.subTest(purpose=purpose):
                struct = next(iter(types.values()))
                caller_fields = {
                    field["name"]: stressed(field)
                    for field in struct
                    if field["name"] not in ("wallet", "nonce", "deadline")
                }
                challenge = issue_challenge(purpose, SIGNER.address, caller_fields, verifying_contract=CONTRACT)

                assert_signable(self, challenge_response(challenge))

    @override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
    def test_the_swap_payload_survives_an_eighteen_decimal_amount(self):
        swap = self.tenant.swap
        asset = swap.payment_asset
        asset.decimals = 18
        asset.save(update_fields=["decimals"])
        SwapOrder.objects.filter(pk=swap.pk).update(payment_amount=int(Decimal("2.50") * (10**18)))
        swap.refresh_from_db()

        with patch("tokens.services.atomic_swap_service.get_base_chain_client") as client, patch(
            "tokens.services.atomic_swap_service.WhitelistService"
        ):
            client.return_value.chain_id = 84532
            typed_data = AtomicSwapService().get_typed_data(swap)

        self.assertGreater(swap.payment_amount, JAVASCRIPT_SAFE_INTEGER)
        assert_signable(self, typed_data)

    def test_the_rule_recognises_a_value_a_javascript_client_would_round(self):
        self.assertEqual(unsafe_numbers({"a": [{"b": OVER_THE_LIMIT}]}), [OVER_THE_LIMIT])
        self.assertEqual(unsafe_numbers({"a": [{"b": JAVASCRIPT_SAFE_INTEGER}]}), [])
        self.assertEqual(unsafe_numbers({"a": str(OVER_THE_LIMIT)}), [])
