from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from drf_spectacular.generators import SchemaGenerator
from eth_account.messages import _hash_eip191_message, encode_typed_data
from jsonschema import Draft7Validator, RefResolver
from rest_framework.test import APIClient, APITransactionTestCase
from web3 import Web3

from assets.models import AssetChainDeployment
from blockchain.models import TransactionStatus
from feature_flags.models import FeatureFlag
from shared.db import current_alias, set_principal, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.settlement import save_swap_with_context
from shared.tests.tenants import make_tenant
from tokens.exceptions import SettlementContextChanged, SwapSignatureException
from tokens.models import ShareToken, SwapOrderStatus, TransferOrder
from tokens.services import atomic_swap_service
from tokens.services.atomic_swap_service import MAX_UINT256
from tokens.services.settlement_context import (
    recorded_settlement_context,
)
from tokens.services.trading_order_access import require_pending_settlement
from tokens.tests.swap_state_fixtures import (
    BUYER,
    CONFIRMED,
    CONTRACT,
    SELLER,
    TX_HASH,
    make_swap,
    persisted_outcome,
    swap_service,
)
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet


def json_schema_with_nullability(value):
    if isinstance(value, list):
        return [json_schema_with_nullability(item) for item in value]
    if not isinstance(value, dict):
        return value
    schema = {key: json_schema_with_nullability(item) for key, item in value.items() if key != "nullable"}
    return {"anyOf": [schema, {"type": "null"}]} if value.get("nullable") else schema


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
class SwapSettlementContextTest(TestCase):
    def test_payment_selection_preserves_nullable_sides_and_buyer_precedence(self):
        tenant = make_tenant("context-payment-selection")
        selected = tenant.refs.stablecoin
        other = tenant.refs.spare_asset
        for seller_payment, buyer_payment in ((None, selected), (selected, None), (other, selected)):
            with self.subTest(seller=seller_payment, buyer=buyer_payment):
                tenant.order.payment_asset = seller_payment
                tenant.order.save(update_fields=["payment_asset"])
                tenant.counter_order.payment_asset = buyer_payment
                tenant.counter_order.save(update_fields=["payment_asset"])
                swap = atomic_swap_service.create_swap_order(tenant.order, tenant.counter_order, share_amount=2)
                context = recorded_settlement_context(swap)
                self.assertEqual(swap.payment_asset_id, selected.pk)
                self.assertEqual(context["payment_asset"]["uuid"], str(selected.pk))
                self.assertEqual(
                    context["seller"]["payment_asset_uuid"], str(seller_payment.pk) if seller_payment else None
                )
                self.assertEqual(
                    context["buyer"]["payment_asset_uuid"], str(buyer_payment.pk) if buyer_payment else None
                )
                self.assertEqual(context["typed_data"]["message"]["paymentAmount"], "300")

    def test_actual_match_creation_captures_context_without_constructing_a_provider(self):
        tenant = make_tenant("context-create")
        with patch("tokens.services.atomic_swap_service.get_base_chain_client") as provider:
            service = atomic_swap_service
            swap = service.create_swap_order(tenant.order, tenant.counter_order, share_amount=3)
        provider.assert_not_called()
        context = recorded_settlement_context(swap)
        self.assertEqual(context["seller"]["owner_account_uuid"], str(tenant.account.pk))
        self.assertEqual(context["buyer"]["wallet_uuid"], str(tenant.wallet.pk))
        self.assertEqual(context["typed_data"]["message"]["shareAmount"], "3")
        self.assertEqual(context["typed_data"]["message"]["paymentAmount"], "450")
        self.assertEqual(context["payment_asset"]["pricing_decimals"], 2)
        self.assertEqual(context["payment_asset"]["deployment_decimals"], 2)
        self.assertAlmostEqual((swap.expires_at - swap.created_at).total_seconds(), 900, delta=2)

    def test_large_exact_amounts_full_digest_and_distinct_equal_matches(self):
        tenant = make_tenant("context-large")
        amount = 9007199254740993
        TransferOrder.objects.filter(pk__in=[tenant.order.pk, tenant.counter_order.pk]).update(quantity=amount)
        service = atomic_swap_service
        first = service.create_swap_order(tenant.order, tenant.counter_order, share_amount=amount)
        second = service.create_swap_order(tenant.order, tenant.counter_order, share_amount=amount)
        message = service.get_typed_data(first)
        self.assertEqual(message["message"]["shareAmount"], "9007199254740993")
        self.assertEqual(message["message"]["paymentAmount"], "1351079888211148950")
        signable = encode_typed_data(full_message=message)
        self.assertEqual(first.order_hash, signable.body.hex())
        self.assertEqual(first.settlement_digest, "0x" + _hash_eip191_message(signable).hex())
        self.assertNotEqual(first.nonce, second.nonce)
        self.assertNotEqual(first.settlement_digest, second.settlement_digest)

    def test_captured_context_survives_config_and_display_changes_but_new_work_refuses(self):
        swap = make_swap("context-drift")
        service = swap_service(self)
        original = deepcopy(service.get_typed_data(swap))
        for changes in (
            {"ATOMIC_SWAP_ADDRESS": "0x" + "76" * 20},
            {"BLOCKCHAIN_CHAIN_ID": 11155111},
        ):
            with self.subTest(changes=changes), override_settings(**changes):
                self.assertEqual(service.get_typed_data(swap), original)
                with self.assertRaises(SettlementContextChanged):
                    require_pending_settlement(swap)
        ShareToken.objects.filter(pk=swap.share_token_id).update(name="Later display", symbol="LATER")
        self.assertEqual(require_pending_settlement(swap)["share_token"]["symbol"], "DEP")
        ShareToken.objects.filter(pk=swap.share_token_id).update(contract_address="0x" + "77" * 20)
        self.assertEqual(service.get_typed_data(swap), original)
        with self.assertRaises(SettlementContextChanged):
            service.check_swap_allowances(swap)
        service.get_base_chain_client().load_contract.assert_not_called()

    def test_deployment_and_scale_drift_refuse_without_reinterpreting_recorded_amounts(self):
        swap = make_swap("context-scale")
        context = recorded_settlement_context(swap)
        deployment_id = context["payment_asset"]["deployment_uuid"]
        AssetChainDeployment.objects.filter(pk=deployment_id).update(decimals=6)
        with self.assertRaises(SettlementContextChanged):
            require_pending_settlement(swap)
        self.assertEqual(recorded_settlement_context(swap), context)
        AssetChainDeployment.objects.filter(pk=deployment_id).update(decimals=2, is_active=False)
        with self.assertRaises(SettlementContextChanged):
            require_pending_settlement(swap)

    def test_provider_chain_is_checked_and_drift_during_that_call_is_rechecked(self):
        swap = make_swap("context-provider")
        service = swap_service(self)
        service.get_base_chain_client().assert_expected_chain.return_value = 1
        with self.assertRaises(SettlementContextChanged):
            service.check_swap_allowances(swap)
        service.get_base_chain_client().load_contract.assert_not_called()

        def drift():
            ShareToken.objects.filter(pk=swap.share_token_id).update(contract_address="0x" + "75" * 20)
            return settings.BLOCKCHAIN_CHAIN_ID

        service.get_base_chain_client().assert_expected_chain.side_effect = drift
        with self.assertRaises(SettlementContextChanged):
            service.get_approval_transaction_data(swap, "seller")
        service.get_base_chain_client().load_contract.assert_not_called()

    def test_wrong_domain_and_changed_message_signatures_refuse_but_original_replays(self):
        swap = make_swap("context-signatures")
        service = swap_service(self)
        original = service.get_typed_data(swap)
        for section, field, value in (
            ("domain", "chainId", "11155111"),
            ("domain", "verifyingContract", "0x" + "74" * 20),
            ("message", "shareToken", "0x" + "73" * 20),
            ("message", "shareAmount", "11"),
            ("message", "nonce", str(swap.nonce + 1)),
            ("message", "deadline", "1"),
        ):
            altered = deepcopy(original)
            altered[section][field] = value
            signature = "0x" + SELLER.sign_message(encode_typed_data(full_message=altered)).signature.hex()
            with self.subTest(field=field), self.assertRaises(SwapSignatureException):
                service.submit_signature(swap, signature, SELLER.address)
        signature = "0x" + SELLER.sign_message(encode_typed_data(full_message=original)).signature.hex()
        with patch("tokens.services.atomic_swap_service.publish_trading_event") as event:
            service.submit_signature(swap, signature, SELLER.address)
            service.submit_signature(swap, signature, SELLER.address)
        self.assertEqual(event.call_count, 1)
        service.get_base_chain_client().load_contract.assert_not_called()


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "33" * 32)
class SwapSettlementExecutionTest(APITransactionTestCase):
    def setUp(self):
        event = patch("tokens.services.atomic_swap_service.publish_trading_event")
        event.start()
        self.addCleanup(event.stop)

    def test_claim_records_complete_original_signed_args_and_receipt_uses_original_domain(self):
        swap = make_swap("context-claim", ready=True)
        service = swap_service(self)
        claimed, transaction = service._claim_execution(swap.pk)
        context = recorded_settlement_context(claimed)
        self.assertEqual(transaction.function_args.get("deadline"), context["typed_data"]["message"]["deadline"])
        self.assertEqual(transaction.function_args["sellerSignature"], swap.seller_signature)
        self.assertEqual(transaction.function_args["settlement"]["digest"], swap.settlement_digest)
        self.assertEqual(transaction.to_address, context["typed_data"]["domain"]["verifyingContract"])
        service._record_sent(claimed, transaction, TX_HASH)
        with use_operator():
            claimed.refresh_from_db()
        contract = service.get_base_chain_client().load_contract.return_value
        contract.events.SwapExecuted.return_value.process_receipt.return_value = [
            {"args": {"orderHash": swap.settlement_digest}}
        ]
        service.get_base_chain_client().receipt_even_if_reverted.return_value = CONFIRMED
        with override_settings(ATOMIC_SWAP_ADDRESS="0x" + "72" * 20):
            self.assertEqual(service.resolve_executing_swap(claimed), "executed")
        service.get_base_chain_client().load_contract.assert_called_with(
            "AtomicSwap", context["typed_data"]["domain"]["verifyingContract"]
        )
        with use_operator():
            claimed.refresh_from_db()
        self.assertEqual(claimed.status, SwapOrderStatus.COMPLETED)

    def test_drift_before_claim_prevents_claim_and_drift_after_prepare_keeps_reservation(self):
        swap = make_swap("context-send-drift", ready=True)
        service = swap_service(self)
        before = persisted_outcome(swap)
        with override_settings(ATOMIC_SWAP_ADDRESS="0x" + "71" * 20), self.assertRaises(SettlementContextChanged):
            service.execute_swap(swap)
        self.assertEqual(persisted_outcome(swap), before)

        def prepare(_swap):
            ShareToken.objects.filter(pk=swap.share_token_id).update(contract_address="0x" + "70" * 20)
            return b"synthetic-unused"

        with patch.object(service, "validate_swap_balances"), patch.object(
            service, "_prepare_attempt", side_effect=prepare
        ):
            with self.assertRaises(SettlementContextChanged):
                service.execute_swap(swap)
        with use_operator():
            swap.refresh_from_db()
        self.assertEqual(swap.status, SwapOrderStatus.EXECUTING)
        self.assertEqual(swap.transaction.status, TransactionStatus.PENDING)
        self.assertEqual(swap.sell_order.filled_quantity, 30)
        service.get_base_chain_client().send_raw_transaction.assert_not_called()


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
class SwapSettlementRouteTest(APITransactionTestCase):
    def setUp(self):
        event = patch("tokens.services.atomic_swap_service.publish_trading_event")
        event.start()
        self.addCleanup(event.stop)
        with use_operator():
            FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
            self.swap = make_swap("context-route")
            self.seller_order = self.swap.sell_order
            self.buyer_order = self.swap.buy_order
            Wallet.objects.filter(pk__in=[self.swap.seller_wallet_id, self.swap.buyer_wallet_id]).update(
                verification_status=WALLET_VERIFICATION_STATUS_VERIFIED
            )
            self.user = self.seller_order.owner_account.user_profile.user
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.identity = {
            "swap_uuid": str(self.swap.pk),
            "owner_account_uuid": str(self.seller_order.owner_account_id),
            "wallet_uuid": str(self.swap.seller_wallet_id),
            "settlement_digest": self.swap.settlement_digest,
        }
        self.url = f"/api/v1/trading/orders/{self.seller_order.pk}/swap"

    def test_signing_schema_requires_recorded_context_and_decimal_string_chain_id(self):
        document = SchemaGenerator().get_schema(request=None, public=True)
        response = self.client.get(self.url + "/", self.identity)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        components = document["components"]["schemas"]
        self.assertNotIn("LegacySwapOrderForSigning", components)
        response_schema = document["paths"]["/api/v1/trading/orders/{uuid}/swap/"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        self.assertEqual(response_schema, {"$ref": "#/components/schemas/SettlementSwapOrderForSigning"})
        typed_data = Draft7Validator(
            components["SettlementSwapOrderForSigning"]["properties"]["typedData"],
            resolver=RefResolver.from_schema(document),
        )
        context = Draft7Validator(
            components["SettlementSwapOrder"]["properties"]["settlementContext"],
            resolver=RefResolver.from_schema(document),
        )
        self.assertEqual(list(typed_data.iter_errors(body["typedData"])), [])
        self.assertEqual(list(context.iter_errors(body["swapOrder"]["settlementContext"])), [])
        legacy_data = deepcopy(body["typedData"])
        legacy_data["domain"]["chainId"] = int(legacy_data["domain"]["chainId"])
        self.assertIsInstance(legacy_data["domain"]["chainId"], int)
        self.assertIsInstance(body["typedData"]["domain"]["chainId"], str)
        self.assertFalse(typed_data.is_valid(legacy_data))
        for source in (body["typedData"], legacy_data):
            invalid = deepcopy(source)
            invalid["message"]["shareAmount"] = 9007199254740993
            self.assertFalse(typed_data.is_valid(invalid))
        invalid_party = deepcopy(body["swapOrder"]["settlementContext"])
        del invalid_party["seller"]["walletUuid"]
        invalid_chain = deepcopy(body["swapOrder"]["settlementContext"])
        invalid_chain["typedData"]["domain"]["chainId"] = 84532
        invalid_types = deepcopy(body["swapOrder"]["settlementContext"])
        invalid_types["typedData"]["types"]["SwapOrder"][0]["type"] = 1
        for invalid in (invalid_party, invalid_chain, invalid_types):
            with self.subTest(invalid=invalid):
                self.assertFalse(context.is_valid(invalid))

    def test_exact_recovery_preserves_original_display_after_expiry_and_config_drift(self):
        ShareToken.objects.filter(pk=self.swap.share_token_id).update(name="Changed", symbol="CHANGED")
        with override_settings(ATOMIC_SWAP_ADDRESS="0x" + "69" * 20):
            response = self.client.get(self.url + "/", self.identity)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["swapOrder"]["shareTokenSymbol"], "DEP")
        self.assertEqual(body["typedData"]["message"]["shareAmount"], "10")
        self.assertFalse(body["canSign"])
        with patch("django.utils.timezone.now", return_value=self.swap.expires_at + timedelta(seconds=1)):
            expired = self.client.get(self.url + "/", self.identity)
        self.assertEqual(expired.status_code, 200, expired.content)
        self.assertFalse(expired.json()["canSign"])
        self.assertEqual(expired.json()["settlementDigest"], self.swap.settlement_digest)

    def test_new_context_refuses_unpinned_and_foreign_wallet_but_allows_owned_lookup(self):
        unpinned = self.client.get(self.url + "/", {"wallet_address": SELLER.address})
        self.assertEqual(unpinned.status_code, 400)
        with use_operator():
            other = make_tenant("context-foreign")
        wrong = self.client.get(self.url + "/", {**self.identity, "wallet_uuid": str(other.wallet.pk)})
        self.assertEqual(wrong.status_code, 404)
        correct = self.client.get(self.url + "/", self.identity)
        self.assertEqual(correct.status_code, 200, correct.content)

    def request_swap_action(self, action, identity):
        url = self.url + "/" + (action + "/" if action else "")
        if action == "sign":
            signature = SELLER.sign_message(
                encode_typed_data(full_message=atomic_swap_service.get_typed_data(self.swap))
            ).signature.hex()
            return self.client.post(
                url, {**identity, "signature": "0x" + signature, "signer_address": SELLER.address}, format="json"
            )
        if action == "approval-broadcast":
            raw = SELLER.sign_transaction(self.approval_transaction()).raw_transaction.hex()
            return self.client.post(url, {**identity, "signed_transaction": raw}, format="json")
        return self.client.get(url, identity)

    def test_missing_identity_fields_refuse_before_effects_with_a_valid_signing_control(self):
        with use_operator():
            before = persisted_outcome(self.swap)
        fields = {"swap_uuid": "swapUuid", "owner_account_uuid": "ownerAccountUuid", "wallet_uuid": "walletUuid"}
        with patch("tokens.services.atomic_swap_service.get_base_chain_client") as provider, patch(
            "tokens.services.atomic_swap_service.publish_trading_event"
        ) as event:
            provider.side_effect = AssertionError("Incomplete identity must not reach a provider")
            for action in ("", "approval-status", "approval-data", "sign", "approval-broadcast"):
                for missing in (*[(field,) for field in fields], tuple(self.identity)):
                    identity = {name: value for name, value in self.identity.items() if name not in missing}
                    with self.subTest(action=action, missing=missing):
                        refused = self.request_swap_action(action, {"wallet_address": SELLER.address, **identity})
                        self.assertEqual(refused.status_code, 400, refused.content)
                        for field in missing:
                            if field in fields:
                                self.assertIn(fields[field], refused.json())
            provider.assert_not_called()
            event.assert_not_called()
            with use_operator():
                self.assertEqual(persisted_outcome(self.swap), before)
            accepted = self.request_swap_action("sign", self.identity)
            self.assertEqual(accepted.status_code, 200, accepted.content)
            event.assert_called_once()
            provider.assert_not_called()
        with use_operator():
            self.swap.refresh_from_db()
        self.assertTrue(self.swap.seller_signature)
        self.assertFalse(self.swap.buyer_signature)

    def test_missing_or_malformed_action_digest_refuses_before_effects(self):
        with use_operator():
            before = persisted_outcome(self.swap)
        with patch("tokens.services.atomic_swap_service.get_base_chain_client") as provider, patch(
            "tokens.services.atomic_swap_service.publish_trading_event"
        ) as event:
            provider.side_effect = AssertionError("Invalid digest must not reach a provider")
            for action in ("approval-status", "approval-data", "sign", "approval-broadcast"):
                for digest in (None, "", "not-a-digest", "0x" + "F" * 64):
                    identity = {name: value for name, value in self.identity.items() if name != "settlement_digest"}
                    if digest is not None:
                        identity["settlement_digest"] = digest
                    with self.subTest(action=action, digest=digest):
                        refused = self.request_swap_action(action, identity)
                        self.assertEqual(refused.status_code, 400, refused.content)
                        self.assertIn("settlementDigest", refused.json())
                refused = self.request_swap_action(action, {**self.identity, "settlement_digest": "0x" + "00" * 32})
                self.assertEqual(refused.status_code, 409, refused.content)
            event.assert_not_called()
            with use_operator():
                self.assertEqual(persisted_outcome(self.swap), before)
            positive = self.request_swap_action("", self.identity)
            self.assertEqual(positive.status_code, 200, positive.content)
            provider.assert_not_called()

    def test_each_private_participant_can_fetch_original_context_without_a_digest(self):
        with use_operator():
            buyer = make_tenant("context-private-buyer", with_swap=False)
            wallet = Wallet.objects.create(
                user_account=buyer.account,
                address=BUYER.address,
                chain="base",
                verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
            )
            order = TransferOrder.objects.create(
                token=self.swap.share_token,
                payment_asset=self.swap.payment_asset,
                wallet=wallet,
                owner_account=buyer.account,
                wallet_address=wallet.address,
                order_type="buy",
                quantity=10,
                price_per_share="1.50",
            )
            swap = save_swap_with_context(
                sell_order=self.seller_order,
                buy_order=order,
                share_token=self.swap.share_token,
                payment_asset=self.swap.payment_asset,
                seller_address=SELLER.address,
                buyer_address=BUYER.address,
                share_amount=10,
                payment_amount=1500,
                nonce=self.swap.nonce + 1,
            )
        self.assertNotEqual(self.user.pk, buyer.user.pk)
        parties = (("seller", self.user, self.seller_order), ("buyer", buyer.user, order))
        with patch("tokens.services.atomic_swap_service.get_base_chain_client") as provider:
            provider.side_effect = AssertionError("Saved context lookup must not reach a provider")
            for role, user, recorded_order in parties:
                with self.subTest(role=role):
                    self.client.force_authenticate(user)
                    identity = {
                        "swap_uuid": str(swap.pk),
                        "owner_account_uuid": str(recorded_order.owner_account_id),
                        "wallet_uuid": str(recorded_order.wallet_id),
                    }
                    url = f"/api/v1/trading/orders/{recorded_order.pk}/swap/"
                    response = self.client.get(url, identity)
                    self.assertEqual(response.status_code, 200, response.content)
                    body = response.json()
                    self.assertEqual(body["settlementDigest"], swap.settlement_digest)
                    self.assertEqual(body["swapUuid"], str(swap.pk))
                    self.assertEqual(body["orderUuid"], str(recorded_order.pk))
                    self.assertEqual(body["walletUuid"], str(recorded_order.wallet_id))
                    self.assertEqual(body["ownerAccountUuid"], str(recorded_order.owner_account_id))
                    self.assertEqual(body["userRole"], role)
                    self.assertEqual(body["typedData"]["message"]["paymentAmount"], "1500")
            provider.assert_not_called()

    def test_counterparty_signature_relay_preserves_caller_wallet_scope(self):
        signature = (
            "0x"
            + SELLER.sign_message(
                encode_typed_data(full_message=atomic_swap_service.get_typed_data(self.swap))
            ).signature.hex()
        )
        buyer_identity = {**self.identity, "wallet_uuid": str(self.swap.buyer_wallet_id)}
        url = f"/api/v1/trading/orders/{self.buyer_order.pk}/swap/sign/"
        response = self.client.post(
            url, {**buyer_identity, "signature": signature, "signer_address": SELLER.address}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        with use_operator():
            self.swap.refresh_from_db()
        self.assertEqual(self.swap.seller_signature, signature)
        self.assertFalse(self.swap.buyer_signature)

    def test_scoped_signer_address_refuses_nonhex_and_accepts_valid_case_variants(self):
        signature = (
            "0x"
            + SELLER.sign_message(
                encode_typed_data(full_message=atomic_swap_service.get_typed_data(self.swap))
            ).signature.hex()
        )
        self.client.raise_request_exception = False
        response = self.client.post(
            self.url + "/sign/",
            {**self.identity, "signature": signature, "signer_address": "0x" + "z" * 40},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("signerAddress", response.json())
        with use_operator():
            self.swap.refresh_from_db()
        self.assertFalse(self.swap.seller_signature)
        for address in (SELLER.address, "0x" + SELLER.address[2:].upper(), SELLER.address.lower()):
            with self.subTest(address=address):
                accepted = self.client.post(
                    self.url + "/sign/",
                    {**self.identity, "signature": signature, "signer_address": address},
                    format="json",
                )
                self.assertEqual(accepted.status_code, 200, accepted.content)
        with use_operator():
            self.swap.refresh_from_db()
        self.assertEqual(self.swap.seller_signature, signature)

    def test_wallet_retirement_during_signature_check_prevents_persistence(self):
        service = atomic_swap_service
        signature = (
            "0x"
            + SELLER.sign_message(encode_typed_data(full_message=service.get_typed_data(self.swap))).signature.hex()
        )
        original = atomic_swap_service.verify_signature

        def retire(instance, *args):
            result = original(instance, *args)
            Wallet.objects.filter(pk=self.swap.seller_wallet_id).update(verification_status="unverified")
            return result

        with patch.object(atomic_swap_service, "verify_signature", retire):
            response = self.client.post(
                self.url + "/sign/",
                {**self.identity, "signature": signature, "signer_address": SELLER.address},
                format="json",
            )
        self.assertEqual(response.status_code, 404, response.content)
        with use_operator():
            self.swap.refresh_from_db()
        self.assertFalse(self.swap.seller_signature)

    def test_configuration_drift_during_signature_check_does_not_store_the_valid_signature(self):
        typed = atomic_swap_service.get_typed_data(self.swap)
        signature = "0x" + SELLER.sign_message(encode_typed_data(full_message=typed)).signature.hex()
        original = atomic_swap_service.verify_signature

        def drift(instance, *args):
            result = original(instance, *args)
            with use_operator():
                ShareToken.objects.filter(pk=self.swap.share_token_id).update(contract_address="0x" + "6a" * 20)
            return result

        with patch.object(atomic_swap_service, "verify_signature", drift):
            response = self.client.post(
                self.url + "/sign/",
                {**self.identity, "signature": signature, "signer_address": SELLER.address},
                format="json",
            )
        self.assertEqual(response.status_code, 409, response.content)
        with use_operator():
            self.swap.refresh_from_db()
        self.assertFalse(self.swap.seller_signature)
        recovered = self.client.get(self.url + "/", self.identity)
        self.assertEqual(recovered.status_code, 200, recovered.content)
        self.assertEqual(recovered.json()["typedData"], typed)
        self.assertFalse(recovered.json()["canSign"])

    def test_exact_lookup_ignores_a_newer_swap_and_refuses_a_different_digest(self):
        with use_operator():
            newer = atomic_swap_service.create_swap_order(self.seller_order, self.buyer_order)
        self.assertNotEqual(newer.pk, self.swap.pk)
        response = self.client.get(self.url + "/", self.identity)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["swapUuid"], str(self.swap.pk))
        wrong = self.client.get(self.url + "/", {**self.identity, "settlement_digest": newer.settlement_digest})
        self.assertEqual(wrong.status_code, 409, wrong.content)

    def test_wallet_retirement_during_allowance_lookup_refuses_the_late_result(self):
        service = swap_service(self)
        self.enterContext(patch.object(service, "check_allowance", lambda *_args: 0))
        with patch("tokens.views.trading_order.atomic_swap_service", service):
            positive = self.client.get(self.url + "/approval-status/", self.identity)
        self.assertEqual(positive.status_code, 200, positive.content)

        def retire(*_args):
            with use_operator():
                Wallet.objects.filter(pk=self.swap.seller_wallet_id).update(verification_status="unverified")
            return 0

        self.enterContext(patch.object(service, "check_allowance", retire))
        with patch("tokens.views.trading_order.atomic_swap_service", service):
            refused = self.client.get(self.url + "/approval-status/", self.identity)
        self.assertEqual(refused.status_code, 404, refused.content)

    def test_sufficient_approval_echoes_identity_and_exact_integers(self):
        service = swap_service(self)
        self.enterContext(patch.object(service, "check_allowance", lambda *_args: MAX_UINT256))
        with patch("tokens.views.trading_order.atomic_swap_service", service):
            response = self.client.get(self.url + "/approval-data/", self.identity)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["swapUuid"], str(self.swap.pk))
        self.assertEqual(body["walletUuid"], str(self.swap.seller_wallet_id))
        self.assertEqual(body["settlementDigest"], self.swap.settlement_digest)
        self.assertEqual(body["currentAllowance"], str(MAX_UINT256))
        self.assertFalse(body["needsApproval"])

    def test_scoped_approval_variants_match_the_actual_generated_response_contract(self):
        document = SchemaGenerator().get_schema(request=None, public=True)
        service = swap_service(self)
        service.get_base_chain_client().build_transaction.return_value = {
            "data": "0x1234",
            "gas": 50000,
            "gasPrice": 1,
            "nonce": 0,
        }
        for action, allowance in (("approval-status", 0), ("approval-data", 0), ("approval-data", MAX_UINT256)):
            with self.subTest(action=action, allowance=allowance):
                self.enterContext(patch.object(service, "check_allowance", lambda *_args: allowance))
                with patch("tokens.views.trading_order.atomic_swap_service", service):
                    response = self.client.get(self.url + f"/{action}/", self.identity)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["settlementDigest"], self.swap.settlement_digest)
                schema = document["paths"][f"/api/v1/trading/orders/{{uuid}}/swap/{action}/"]["get"]["responses"][
                    "200"
                ]["content"]["application/json"]["schema"]
                errors = list(
                    Draft7Validator(schema, resolver=RefResolver.from_schema(document)).iter_errors(response.json())
                )
                self.assertEqual([error.message for error in errors], [])

    def test_signatures_require_exact_identity_and_digest_in_the_generated_request_contract(self):
        document = SchemaGenerator().get_schema(request=None, public=True)
        schema = document["paths"]["/api/v1/trading/orders/{uuid}/swap/sign/"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        signature = (
            "0x"
            + SELLER.sign_message(
                encode_typed_data(full_message=atomic_swap_service.get_typed_data(self.swap))
            ).signature.hex()
        )
        legacy = {"signature": signature, "signerAddress": SELLER.address}
        scoped = {
            **legacy,
            "swapUuid": str(self.swap.pk),
            "ownerAccountUuid": str(self.seller_order.owner_account_id),
            "walletUuid": str(self.swap.seller_wallet_id),
            "settlementDigest": self.swap.settlement_digest,
        }
        validator = Draft7Validator(schema, resolver=RefResolver.from_schema(document))
        self.assertEqual([error.message for error in validator.iter_errors(scoped)], [])
        self.assertFalse(validator.is_valid(legacy))
        for field in scoped:
            with self.subTest(missing=field):
                self.assertFalse(validator.is_valid({name: value for name, value in scoped.items() if name != field}))
        self.assertTrue(list(validator.iter_errors({})))
        response = self.client.post(self.url + "/sign/", scoped, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        response_schema = document["paths"]["/api/v1/trading/orders/{uuid}/swap/sign/"]["post"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        self.assertEqual(response_schema, {"$ref": "#/components/schemas/SettlementSwapOrder"})
        response_validator = Draft7Validator(
            response_schema, resolver=RefResolver.from_schema(json_schema_with_nullability(document))
        )
        self.assertEqual(
            [(list(error.path), error.message) for error in response_validator.iter_errors(response.json())], []
        )
        legacy_response = {**response.json(), "settlementProtocolVersion": 0, "settlementContext": None}
        self.assertFalse(response_validator.is_valid(legacy_response))
        with use_operator():
            self.swap.refresh_from_db()
        self.assertEqual(self.swap.seller_signature, signature)

    def approval_transaction(self):
        context = recorded_settlement_context(self.swap)
        spender = context["typed_data"]["domain"]["verifyingContract"]
        data = "0x095ea7b3" + spender[2:].rjust(64, "0") + f"{MAX_UINT256:064x}"
        tx = {
            "to": context["share_token"]["address"],
            "chainId": settings.BLOCKCHAIN_CHAIN_ID,
            "value": 0,
            "data": data,
            "gas": 50000,
            "gasPrice": 1,
            "nonce": 0,
        }
        return tx

    def test_signed_approval_checks_actual_chain_target_spender_amount_and_owner(self):
        tx = self.approval_transaction()
        data = tx["data"]
        service = swap_service(self)
        provider = service.get_base_chain_client()
        with patch("tokens.views.trading_order.atomic_swap_service", service), patch(
            "tokens.services.token_transfer_service.get_base_chain_client", return_value=provider
        ) as factory, patch("tokens.services.token_transfer_service.whitelist"):
            for changes in ({"chainId": 1}, {"to": "0x" + "68" * 20}, {"value": 1}, {"data": data[:-1] + "0"}):
                raw = SELLER.sign_transaction({**tx, **changes}).raw_transaction.hex()
                with self.subTest(changes=changes):
                    response = self.client.post(
                        self.url + "/approval-broadcast/", {**self.identity, "signed_transaction": raw}, format="json"
                    )
                    self.assertEqual(response.status_code, 409, response.content)
            wrong_owner = BUYER.sign_transaction(tx).raw_transaction.hex()
            response = self.client.post(
                self.url + "/approval-broadcast/", {**self.identity, "signed_transaction": wrong_owner}, format="json"
            )
            self.assertEqual(response.status_code, 409, response.content)
            factory.assert_not_called()
            provider.send_raw_transaction.assert_not_called()
            raw = SELLER.sign_transaction(tx).raw_transaction.hex()
            expected_hash = Web3.to_hex(Web3.keccak(bytes.fromhex(raw)))
            provider.send_raw_transaction.return_value = expected_hash
            provider.wait_for_receipt.return_value = {**CONFIRMED, "transactionHash": bytes.fromhex(expected_hash[2:])}
            success = self.client.post(
                self.url + "/approval-broadcast/", {**self.identity, "signed_transaction": raw}, format="json"
            )
            self.assertEqual(success.status_code, 200, success.content)
            self.assertEqual(success.json()["txHash"], expected_hash)
            provider.send_raw_transaction.assert_called_once_with(bytes.fromhex(raw))
            provider.wait_for_receipt.assert_called_once_with(expected_hash)

    def test_approval_receipt_identity_and_uncertain_send_keep_original_attribution(self):
        raw = SELLER.sign_transaction(self.approval_transaction()).raw_transaction.hex()
        expected_hash = Web3.to_hex(Web3.keccak(bytes.fromhex(raw)))
        for returned, observed, status, failure in (
            (TX_HASH, expected_hash, 1, None),
            (None, expected_hash, 1, None),
            ("malformed", expected_hash, 1, None),
            (expected_hash, TX_HASH, 1, None),
            (expected_hash, None, 1, None),
            (expected_hash, "0x1234", 1, None),
            (expected_hash, "0x" + "zz" * 32, 1, None),
            (expected_hash, expected_hash, 0, None),
            (expected_hash, expected_hash, None, None),
            (expected_hash, expected_hash, 1, "send"),
            (expected_hash, expected_hash, 1, "wait"),
        ):
            with self.subTest(returned=returned, observed=observed, status=status, failure=failure):
                service = swap_service(self)
                provider = service.get_base_chain_client()
                provider.send_raw_transaction.return_value = returned
                provider.wait_for_receipt.return_value = {**CONFIRMED, "status": status, "transactionHash": observed}
                if failure:
                    target = provider.send_raw_transaction if failure == "send" else provider.wait_for_receipt
                    target.side_effect = TimeoutError("synthetic provider diagnostic must not reach response")
                with patch("tokens.views.trading_order.atomic_swap_service", service), patch(
                    "tokens.services.token_transfer_service.get_base_chain_client", return_value=provider
                ), patch("tokens.services.token_transfer_service.whitelist"):
                    response = self.client.post(
                        self.url + "/approval-broadcast/", {**self.identity, "signed_transaction": raw}, format="json"
                    )
                self.assertEqual(response.status_code, 503, response.content)
                self.assertEqual(response.json()["code"], "swap_approval_unconfirmed")
                self.assertEqual(response.json()["txHash"], expected_hash)
                self.assertEqual(response.json()["settlementDigest"], self.swap.settlement_digest)
                self.assertEqual(response.json()["swapUuid"], str(self.swap.pk))
                self.assertNotIn("diagnostic", response.content.decode())
                self.assertNotIn("blockNumber", response.json())
                provider.send_raw_transaction.assert_called_once_with(bytes.fromhex(raw))
        with use_operator():
            self.swap.refresh_from_db()
        self.assertFalse(self.swap.tx_hash)
        self.assertIsNone(self.swap.transaction_id)

    def test_matching_approval_receipt_remains_attributed_after_deadline_and_config_change(self):
        raw = SELLER.sign_transaction(self.approval_transaction()).raw_transaction.hex()
        expected_hash = Web3.to_hex(Web3.keccak(bytes.fromhex(raw)))
        service = swap_service(self)
        provider = service.get_base_chain_client()
        provider.send_raw_transaction.return_value = expected_hash
        changed = override_settings(ATOMIC_SWAP_ADDRESS="0x" + "ab" * 20)
        clock = patch("django.utils.timezone.now", return_value=self.swap.expires_at + timedelta(seconds=1))
        self.addCleanup(changed.disable)
        self.addCleanup(clock.stop)

        def after_send(observed):
            self.assertEqual(observed, expected_hash)
            changed.enable()
            clock.start()
            return {**CONFIRMED, "transactionHash": expected_hash}

        provider.wait_for_receipt.side_effect = after_send
        with patch("tokens.views.trading_order.atomic_swap_service", service), patch(
            "tokens.services.token_transfer_service.get_base_chain_client", return_value=provider
        ), patch("tokens.services.token_transfer_service.whitelist"):
            response = self.client.post(
                self.url + "/approval-broadcast/", {**self.identity, "signed_transaction": raw}, format="json"
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["txHash"], expected_hash)
        self.assertEqual(response.json()["settlementDigest"], self.swap.settlement_digest)
        refused = self.client.get(self.url + "/approval-status/", self.identity)
        self.assertEqual(refused.status_code, 400, refused.content)

    def test_nullable_original_payment_reference_is_revalidated_without_reinterpretation(self):
        with use_operator():
            self.buyer_order.payment_asset = None
            self.buyer_order.save(update_fields=["payment_asset"])
            swap = atomic_swap_service.create_swap_order(self.seller_order, self.buyer_order)
        identity = {
            **self.identity,
            "swap_uuid": str(swap.pk),
            "settlement_digest": swap.settlement_digest,
            "wallet_uuid": str(swap.buyer_wallet_id),
        }
        url = f"/api/v1/trading/orders/{self.buyer_order.pk}/swap/"
        allowed = self.client.get(url, identity)
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertIsNone(swap.settlement_context["buyer"]["payment_asset_uuid"])
        with use_operator():
            self.buyer_order.payment_asset_id = swap.payment_asset_id
            self.buyer_order.save(update_fields=["payment_asset"])
        refused = self.client.get(url, identity)
        self.assertEqual(refused.status_code, 404, refused.content)

    def test_another_account_with_the_same_address_does_not_own_the_recorded_side(self):
        with use_operator():
            other = make_tenant("context-same-address")
            wallet = Wallet.objects.create(
                user_account=other.account,
                address=SELLER.address,
                chain="base",
                verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
            )
        self.client.force_authenticate(other.user)
        refused = self.client.get(
            self.url + "/",
            {**self.identity, "owner_account_uuid": str(other.account.pk), "wallet_uuid": str(wallet.pk)},
        )
        self.assertEqual(refused.status_code, 404, refused.content)
        self.client.force_authenticate(self.user)
        positive = self.client.get(self.url + "/", self.identity)
        self.assertEqual(positive.status_code, 200, positive.content)


class ScopedSwapSettlementRouteTest(RunsOnTheScopedConnection, SwapSettlementRouteTest):
    def setUp(self):
        super().setUp()
        set_principal(self.user.pk, current_alias())
