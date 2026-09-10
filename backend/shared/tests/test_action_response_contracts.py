from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from offerings.models import Subscription
from offerings.tests.factories import (
    configure_operator,
    eligible_subscriber,
    open_offering,
)
from shared.tests.tenants import make_eligible, make_tenant, open_to_investors
from tokens.models import ShareIssuance, SwapOrder, TransferOrder
from tokens.services.atomic_swap_service import AtomicSwapService
from tokens.services.token_transfer_service import TokenTransferService
from tokens.tests.test_signed_transactions import SIGNER, sign_legacy
from users.models import FinancialProfile, Notification, UserPreferences, UserProfile
from wallets.models import Wallet


@override_settings(ATOMIC_SWAP_ADDRESS="0x" + "8" * 40)
class ActionResponseContractTest(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document = SchemaGenerator().get_schema(request=None, public=True)

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.owner = make_tenant("schema-owner")
        self.other = make_tenant("schema-other")
        make_eligible(self.owner)
        self.client.force_authenticate(self.owner.user)

    def resolved(self, schema):
        if "$ref" in schema:
            target = self.document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
            return self.resolved({**target, **{key: value for key, value in schema.items() if key != "$ref"}})
        if "allOf" in schema and len(schema["allOf"]) == 1:
            return {
                **self.resolved(schema["allOf"][0]),
                **{key: value for key, value in schema.items() if key != "allOf"},
            }
        return schema

    def response_schema(self, path, method="get", code="200"):
        response = self.document["paths"][path][method]["responses"][code]
        self.assertIn("application/json", response.get("content", {}))
        return self.resolved(response["content"]["application/json"]["schema"])

    def assert_fields(self, schema, body, field_types):
        schema = self.resolved(schema)
        self.assertEqual(set(body), set(field_types))
        self.assertEqual(schema.get("type"), "object")
        self.assertEqual(set(schema["properties"]), set(field_types))
        for name, expected in field_types.items():
            with self.subTest(field=name):
                field = self.resolved(schema["properties"][name])
                if expected == "json":
                    self.assertNotIn("type", field)
                    self.assertTrue(field.get("nullable"))
                    continue
                self.assertEqual(field.get("type"), expected)
                if "enum" in field:
                    self.assertIn(body[name], field["enum"])
                if body[name] is None:
                    self.assertIs(field.get("nullable"), True)
                else:
                    kind = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict}[expected]
                    self.assertIs(type(body[name]), kind)
        self.assertTrue(set(schema.get("required", ())).issubset(body))
        return schema

    def assert_page(self, path, body, item_fields):
        schema = self.assert_fields(
            self.response_schema(path),
            body,
            {"count": "integer", "next": "string", "previous": "string", "results": "array"},
        )
        self.assertEqual(set(schema["required"]), {"count", "results"})
        items = self.resolved(schema["properties"]["results"]["items"])
        self.assertEqual(set(items["properties"]), set(item_fields))
        self.assertTrue(body["results"])
        for row in body["results"]:
            self.assert_fields(items, row, item_fields)
        return items

    def unpaired_order(self):
        return TransferOrder.objects.create(
            token=self.owner.deployed_token,
            payment_asset=self.owner.refs.stablecoin,
            order_type="buy",
            wallet=self.owner.wallet,
            owner_account=self.owner.account,
            wallet_address=self.owner.wallet.address,
            quantity=10,
            min_quantity=0,
            price_per_share=Decimal("1.50"),
        )

    def test_cancel_challenge_declares_the_actual_stored_typed_data(self):
        order = self.unpaired_order()
        response = self.client.get(f"/api/v1/trading/orders/{order.uuid}/cancel/message/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["orderUuid"], str(order.uuid))
        self.assertEqual(body["walletAddress"], order.wallet_address)
        self.assertEqual(body["purpose"], "order_cancel")
        self.assertEqual(body["message"]["orderUuid"], str(order.uuid))
        schema = self.assert_fields(
            self.response_schema("/api/v1/trading/orders/{uuid}/cancel/message/"),
            body,
            {
                "orderUuid": "string",
                "walletAddress": "string",
                "purpose": "string",
                "digest": "string",
                "domain": "object",
                "types": "object",
                "message": "object",
                "expiresAt": "string",
            },
        )
        self.assertEqual(set(schema["required"]), set(body))

    def test_modification_challenge_keeps_numeric_values_and_decimal_text(self):
        order = self.unpaired_order()
        response = self.client.post(
            f"/api/v1/trading/orders/{order.uuid}/modify/message/",
            {"newQuantity": 12, "newMinQuantity": 1, "newPricePerShare": "2.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["currentValues"],
            {"quantity": 10, "minQuantity": 0, "pricePerShare": "1.50", "filledQuantity": 0, "remainingQuantity": 10},
        )
        self.assertEqual(body["newValues"], {"quantity": 12, "minQuantity": 1, "pricePerShare": "2.00"})
        self.assertEqual(body["message"]["newQuantity"], "12")
        schema = self.assert_fields(
            self.response_schema("/api/v1/trading/orders/{uuid}/modify/message/", "post"),
            body,
            {
                "orderUuid": "string",
                "purpose": "string",
                "digest": "string",
                "domain": "object",
                "types": "object",
                "message": "object",
                "expiresAt": "string",
                "currentValues": "object",
                "newValues": "object",
            },
        )
        fields = {"quantity": "integer", "minQuantity": "integer", "pricePerShare": "string"}
        self.assert_fields(schema["properties"]["newValues"], body["newValues"], fields)
        self.assert_fields(
            schema["properties"]["currentValues"],
            body["currentValues"],
            {**fields, "filledQuantity": "integer", "remainingQuantity": "integer"},
        )
        self.assertEqual(set(schema["required"]), set(body))

    def allowance_service(self, sufficient):
        configure_operator(self.owner.refs.stablecoin)
        service = object.__new__(AtomicSwapService)
        service.check_allowance = Mock(return_value=2000 if sufficient else 0)
        service.chain_client = Mock(chain_id=84532)
        service.chain_client.to_checksum_address.side_effect = lambda value: value
        service.chain_client.build_transaction.return_value = {
            "data": "0x1234",
            "gas": 65000,
            "gasPrice": 100,
            "nonce": 3,
        }
        return service

    def approval_request(self, action, sufficient=False):
        service = self.allowance_service(sufficient)
        with patch("tokens.views.trading_order.AtomicSwapService", return_value=service):
            response = self.client.get(
                f"/api/v1/trading/orders/{self.owner.order.uuid}/swap/{action}/",
                {"wallet_address": self.owner.wallet.address},
            )
        self.assertEqual(response.status_code, 200)
        service.check_allowance.assert_called()
        return response.json(), service

    def test_approval_status_declares_integer_allowances(self):
        body, _service = self.approval_request("approval-status")
        self.assertEqual((body["requiredAmount"], body["currentAllowance"]), (10, 0))
        self.assertIs(body["needsApproval"], True)
        schema = self.assert_fields(
            self.response_schema("/api/v1/trading/orders/{uuid}/swap/approval-status/"),
            body,
            {
                "swapUuid": "string",
                "userRole": "string",
                "tokenAddress": "string",
                "tokenSymbol": "string",
                "requiredAmount": "integer",
                "currentAllowance": "integer",
                "needsApproval": "boolean",
                "spender": "string",
            },
        )
        self.assertEqual(set(schema["required"]), set(body))

    def approval_variants(self):
        schema = self.response_schema("/api/v1/trading/orders/{uuid}/swap/approval-data/")
        self.assertEqual(len(schema.get("oneOf", ())), 2)
        variants = [self.resolved(item) for item in schema["oneOf"]]
        return {"transaction" in item["properties"]: item for item in variants}

    def test_approval_no_transaction_variant_keeps_actual_allowance_values(self):
        body, service = self.approval_request("approval-data", sufficient=True)
        self.assertEqual(
            body,
            {
                "needsApproval": False,
                "message": "User already has sufficient allowance",
                "currentAllowance": 2000,
                "requiredAmount": 10,
            },
        )
        service.chain_client.build_transaction.assert_not_called()
        schema = self.assert_fields(
            self.approval_variants()[False],
            body,
            {
                "needsApproval": "boolean",
                "message": "string",
                "currentAllowance": "integer",
                "requiredAmount": "integer",
            },
        )
        self.assertEqual(set(schema["required"]), set(body))

    def test_approval_transaction_variant_keeps_hex_fields_and_decimal_amount(self):
        body, service = self.approval_request("approval-data")
        self.assertIs(body["needsApproval"], True)
        self.assertEqual(body["amount"], str(2**256 - 1))
        self.assertEqual(body["transaction"]["gas"], hex(65000))
        self.assertEqual(body["transaction"]["chainId"], hex(84532))
        service.chain_client.build_transaction.assert_called_once()
        schema = self.assert_fields(
            self.approval_variants()[True],
            body,
            {
                "needsApproval": "boolean",
                "swapUuid": "string",
                "userRole": "string",
                "transaction": "object",
                "description": "string",
                "tokenAddress": "string",
                "tokenSymbol": "string",
                "spender": "string",
                "amount": "string",
                "unlimited": "boolean",
            },
        )
        self.assert_fields(
            schema["properties"]["transaction"],
            body["transaction"],
            {name: "string" for name in ("to", "from", "data", "value", "gas", "gasPrice", "nonce", "chainId")},
        )
        self.assertEqual(set(schema["required"]), set(body))

    def market_response(self):
        response = self.client.get(f"/api/v1/trading/tokens/{self.owner.deployed_token.uuid}/market-data/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        schema = self.assert_fields(
            self.response_schema("/api/v1/trading/tokens/{uuid}/market-data/"),
            body,
            {
                "token": "string",
                "symbol": "string",
                "lastTrade": "object",
                "lastTradePrice": "string",
                "bestBid": "string",
                "bestAsk": "string",
                "midpointPrice": "string",
            },
        )
        self.assertEqual(set(schema["required"]), set(body))
        return body, schema

    def test_market_without_a_trade_keeps_null_trade_fields(self):
        body, _schema = self.market_response()
        self.assertIsNone(body["lastTrade"])
        self.assertIsNone(body["lastTradePrice"])
        self.assertEqual(body["bestBid"], "1.50")

    def test_market_completed_trade_declares_its_actual_nested_shape(self):
        SwapOrder.objects.filter(pk=self.owner.swap.pk).update(status="completed", completed_at=timezone.now())
        body, schema = self.market_response()
        self.assertEqual(body["lastTradePrice"], "1.5")
        self.assertEqual(body["lastTrade"]["paymentAmount"], "15")
        self.assert_fields(
            schema["properties"]["lastTrade"],
            body["lastTrade"],
            {
                "price": "string",
                "shares": "integer",
                "paymentAmount": "string",
                "paymentToken": "string",
                "completedAt": "string",
            },
        )

    def test_order_book_declares_aggregated_arrays_without_changing_the_market(self):
        response = self.client.get(f"/api/v1/trading/tokens/{self.owner.deployed_token.uuid}/order-book/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body,
            {
                "token": str(self.owner.deployed_token.uuid),
                "buyOrders": [{"price": "1.50", "quantity": 10, "orders": 1}],
                "sellOrders": [{"price": "1.50", "quantity": 10, "orders": 1}],
            },
        )
        schema = self.assert_fields(
            self.response_schema("/api/v1/trading/tokens/{uuid}/order-book/"),
            body,
            {"token": "string", "buyOrders": "array", "sellOrders": "array"},
        )
        for name in ("buyOrders", "sellOrders"):
            self.assert_fields(
                schema["properties"][name]["items"],
                body[name][0],
                {"price": "string", "quantity": "integer", "orders": "integer"},
            )

    def test_issuer_subscription_page_declares_the_existing_investor_rows(self):
        response = self.client.get(f"/api/v1/offerings/{self.owner.offering.uuid}/subscriptions/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([row["uuid"] for row in body["results"]], [str(self.owner.subscription.uuid)])
        self.assert_page(
            "/api/v1/offerings/{uuid}/subscriptions/",
            body,
            {
                "uuid": "string",
                "status": "string",
                "statusDisplay": "string",
                "investorName": "string",
                "quantity": "integer",
                "allottedQuantity": "integer",
                "pricePerShare": "string",
                "amountDue": "string",
                "amountReceived": "string",
                "settlementRailDisplay": "string",
                "reference": "string",
                "paymentDueAt": "string",
                "paymentConfirmedAt": "string",
                "allotmentState": "string",
                "walletAddress": "string",
                "createdAt": "string",
            },
        )

    def test_issuance_page_declares_rows_and_nullable_subscription_reference(self):
        issuance = ShareIssuance.objects.create(
            token=self.owner.deployed_token,
            recipient_address=self.owner.wallet.address,
            amount="12",
            status="completed",
            initiated_by=self.owner.user,
            block_number=7,
            completed_at=timezone.now(),
            tx_hash="0x" + "e" * 64,
        )
        response = self.client.get(f"/api/v1/tokens/{self.owner.deployed_token.uuid}/issuances/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["uuid"], str(issuance.uuid))
        self.assert_page(
            "/api/v1/tokens/{uuid}/issuances/",
            body,
            {
                "uuid": "string",
                "token": "string",
                "tokenSymbol": "string",
                "subscriptionReference": "string",
                "recipientAddress": "string",
                "recipientName": "string",
                "amount": "string",
                "issuanceType": "string",
                "issuanceTypeDisplay": "string",
                "reason": "string",
                "status": "string",
                "statusDisplay": "string",
                "txHash": "string",
                "blockNumber": "integer",
                "initiatedBy": "integer",
                "initiatedByEmail": "string",
                "processedAt": "string",
                "completedAt": "string",
                "createdAt": "string",
            },
        )

    def assert_existing_page_boundaries(self, schema_path, endpoint, expected_ids, query_parameters=("page",)):
        parameters = self.document["paths"][schema_path]["get"]["parameters"]
        self.assertEqual({parameter["name"] for parameter in parameters}, {"uuid", *query_parameters})
        first = self.client.get(endpoint)
        second = self.client.get(endpoint, {"page": 2})
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        first, second = first.json(), second.json()
        self.assertEqual((first["count"], second["count"]), (26, 26))
        self.assertEqual((len(first["results"]), len(second["results"])), (25, 1))
        self.assertIsNone(first["previous"])
        self.assertIsNotNone(first["next"])
        self.assertIsNotNone(second["previous"])
        self.assertIsNone(second["next"])
        self.assertEqual({row["uuid"] for row in first["results"] + second["results"]}, expected_ids)
        ignored = self.client.get(
            endpoint,
            {"ordering": "created_at", "company_uuid": str(self.other.company.uuid)},
        )
        self.assertEqual(ignored.status_code, 200)
        self.assertEqual(ignored.json()["results"], first["results"])

    def assert_existing_empty_page(self, schema_path, endpoint):
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"count": 0, "next": None, "previous": None, "results": []})
        self.assert_fields(
            self.response_schema(schema_path),
            response.json(),
            {"count": "integer", "next": "string", "previous": "string", "results": "array"},
        )

    def test_issuer_pages_keep_existing_ordering_and_empty_envelopes(self):
        ids = {str(self.owner.subscription.uuid)}
        for _index in range(25):
            subscription = Subscription.objects.create(
                offering=self.owner.offering,
                user_account=self.owner.account,
                wallet=self.owner.wallet,
                quantity=10,
                price_per_share=Decimal("2.50"),
                amount_due=Decimal("25.00"),
            )
            ids.add(str(subscription.uuid))
        path = "/api/v1/offerings/{uuid}/subscriptions/"
        endpoint = f"/api/v1/offerings/{self.owner.offering.uuid}/subscriptions/"
        self.assert_existing_page_boundaries(path, endpoint, ids)
        Subscription.objects.filter(offering=self.owner.offering).delete()
        self.assert_existing_empty_page(path, endpoint)

    def test_issuance_pages_keep_existing_ordering_and_empty_envelopes(self):
        ids = set()
        completed = set()
        for index in range(26):
            issuance = ShareIssuance.objects.create(
                token=self.owner.deployed_token,
                recipient_address=self.owner.wallet.address,
                amount="12",
                status="completed" if index else "pending",
                completed_at=timezone.now() - timedelta(minutes=index) if index else None,
            )
            ids.add(str(issuance.uuid))
            if index:
                completed.add(str(issuance.uuid))
        path = "/api/v1/tokens/{uuid}/issuances/"
        endpoint = f"/api/v1/tokens/{self.owner.deployed_token.uuid}/issuances/"
        self.assert_existing_page_boundaries(path, endpoint, ids, ("page", "status"))
        filtered = self.client.get(endpoint, {"status": "completed"})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["count"], 25)
        self.assertEqual({row["uuid"] for row in filtered.json()["results"]}, completed)
        pending = self.client.get(endpoint, {"status": "pending"})
        self.assertEqual(pending.status_code, 200)
        self.assertEqual({row["uuid"] for row in pending.json()["results"]}, ids - completed)
        absent = self.client.get(endpoint, {"status": "not-a-status"})
        self.assertEqual(absent.status_code, 200)
        self.assertEqual(absent.json()["results"], [])
        ShareIssuance.objects.filter(token=self.owner.deployed_token).delete()
        self.assert_existing_empty_page(path, endpoint)

    def test_company_stats_declares_all_four_existing_counts(self):
        response = self.client.get(f"/api/v1/companies/{self.owner.company.uuid}/stats/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body, {"totalTokens": 1, "totalShareholders": 0, "pendingActions": 0, "pendingCapitalIncreases": 0}
        )
        self.assert_fields(
            self.response_schema("/api/v1/companies/{uuid}/stats/"), body, {name: "integer" for name in body}
        )

    def test_company_contact_declares_only_the_actual_owner_profile_fields(self):
        UserProfile.objects.filter(user=self.owner.user).update(full_name="Synthetic Contact")
        response = self.client.get(f"/api/v1/companies/{self.owner.company.uuid}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["email"], self.owner.user.email)
        self.assertEqual(body["primaryContact"], {"fullName": "Synthetic Contact"})
        schema = self.response_schema("/api/v1/companies/{uuid}/")
        contact = self.assert_fields(
            schema["properties"]["primaryContact"], body["primaryContact"], {"fullName": "string"}
        )
        self.assertEqual(set(contact["required"]), {"fullName"})
        self.assertTrue(contact["readOnly"])
        self.assertTrue(contact["properties"]["fullName"]["readOnly"])

    def test_company_contact_declares_a_nullable_owner_name(self):
        UserProfile.objects.filter(user=self.owner.user).update(full_name=None)
        response = self.client.get(f"/api/v1/companies/{self.owner.company.uuid}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["primaryContact"], {"fullName": None})
        schema = self.response_schema("/api/v1/companies/{uuid}/")
        contact = self.resolved(schema["properties"]["primaryContact"])
        self.assertTrue(contact["properties"]["fullName"].get("nullable"))
        self.assert_fields(contact, body["primaryContact"], {"fullName": "string"})

    def test_company_contact_declares_an_absent_owner_profile(self):
        endpoint = f"/api/v1/companies/{self.owner.company.uuid}/"
        present = self.client.get(endpoint)
        self.assertEqual(present.status_code, 200)
        self.assertEqual(present.json()["primaryContact"], {"fullName": self.owner.profile.full_name})
        self.owner.profile.delete()
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["primaryContact"])
        schema = self.response_schema("/api/v1/companies/{uuid}/")
        contact = self.resolved(schema["properties"]["primaryContact"])
        self.assertTrue(contact.get("nullable"))
        self.assertTrue(contact["readOnly"])
        self.assertIn("primaryContact", schema["required"])

    def test_notifications_declare_scoped_count(self):
        count = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(count.status_code, 200)
        self.assertEqual(count.json(), {"unreadCount": 1})
        self.assert_fields(
            self.response_schema("/api/notifications/unread-count/"), count.json(), {"unreadCount": "integer"}
        )

    def test_mark_all_read_declares_scoped_update_envelope(self):
        marked = self.client.post("/api/notifications/mark-all-read/")
        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.json(), {"marked": 1})
        self.assert_fields(
            self.response_schema("/api/notifications/mark-all-read/", "post"), marked.json(), {"marked": "integer"}
        )
        self.assertEqual(self.client.get("/api/notifications/unread-count/").json(), {"unreadCount": 0})
        self.assertTrue(Notification.objects.get(pk=self.other.notification.pk).is_read is False)

    def test_delete_account_declares_fixed_success_without_changing_retirement(self):
        response = self.client.post("/api/user-profiles/delete-account/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Your account has been successfully deleted."})
        self.owner.user.refresh_from_db()
        self.other.user.refresh_from_db()
        self.assertFalse(self.owner.user.is_active)
        self.assertTrue(self.other.user.is_active)
        self.assert_fields(
            self.response_schema("/api/user-profiles/delete-account/", "post"), response.json(), {"message": "string"}
        )

    def export_response(self):
        response = self.client.get("/api/user-profiles/export-data/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        schema = self.assert_fields(
            self.response_schema("/api/user-profiles/export-data/"),
            body,
            {
                "exportedAt": "string",
                "user": "object",
                "profile": "object",
                "preferences": "object",
                "financialProfile": "object",
                "accounts": "array",
                "wallets": "array",
                "transactions": "array",
                "portfolios": "array",
            },
        )
        self.assertEqual(set(schema["required"]), set(body))
        return body, schema

    def test_populated_account_export_declares_each_actual_section(self):
        body, schema = self.export_response()
        sections = {
            "user": {"email": "string", "dateJoined": "string", "isEmailVerified": "boolean"},
            "profile": {
                "fullName": "string",
                "dateOfBirth": "string",
                "phoneCountryCode": "string",
                "phoneNumber": "string",
                "residentialAddress": "string",
                "citizenshipCountry": "string",
                "isIdVerified": "boolean",
                "createdAt": "string",
            },
            "preferences": {"selectedPortfolio": "string", "selectedAccount": "string"},
            "financialProfile": {
                "occupation": "string",
                "sourceOfFunds": "json",
                "sourceOfFundsOtherText": "string",
                "intendedUse": "string",
                "intendedUseOtherText": "string",
            },
        }
        for name, fields in sections.items():
            self.assert_fields(schema["properties"][name], body[name], fields)
        arrays = {
            "accounts": {
                "uuid": "string",
                "accountNumber": "string",
                "accountType": "string",
                "activationDate": "string",
                "createdAt": "string",
            },
            "wallets": {
                "uuid": "string",
                "name": "string",
                "chain": "string",
                "address": "string",
                "nativeBalance": "string",
                "marketValue": "string",
                "isVerified": "boolean",
                "createdAt": "string",
            },
            "transactions": {
                "uuid": "string",
                "txHash": "string",
                "chain": "string",
                "status": "string",
                "asset": "string",
                "amount": "string",
                "transactionFee": "string",
                "fromAddress": "string",
                "toAddress": "string",
                "blockTimestamp": "string",
                "createdAt": "string",
            },
            "portfolios": {"uuid": "string", "name": "string", "isActive": "boolean", "createdAt": "string"},
        }
        for name, fields in arrays.items():
            self.assertTrue(body[name])
            for row in body[name]:
                self.assert_fields(schema["properties"][name]["items"], row, fields)
        self.assertEqual({row["uuid"] for row in body["accounts"]}, {str(self.owner.account.uuid)})
        self.assertNotIn(str(self.other.account.uuid), str(body))

    def test_export_preserves_arbitrary_json_source_of_funds(self):
        for value in (["salary"], {"nested": ["salary", 7, None]}, "salary", 7, True, None):
            with self.subTest(value=value):
                FinancialProfile.objects.filter(pk=self.owner.financial_profile.pk).update(source_of_funds=value)
                body, schema = self.export_response()
                self.assertEqual(body["financialProfile"]["sourceOfFunds"], value)
                field = self.resolved(schema["properties"]["financialProfile"])["properties"]["sourceOfFunds"]
                self.assertNotIn("type", field)
                self.assertTrue(field.get("nullable"))

    def test_export_without_a_profile_declares_nullable_sections(self):
        user = get_user_model().objects.create_user(email="schema-bare@example.test", password="pw-12345678")
        self.client.force_authenticate(user)
        body, _schema = self.export_response()
        self.assertEqual([body[name] for name in ("profile", "preferences", "financialProfile")], [None, None, None])
        self.assertEqual(
            [body[name] for name in ("accounts", "wallets", "transactions", "portfolios")], [[], [], [], []]
        )

    def test_export_with_missing_optional_records_keeps_account_rows(self):
        FinancialProfile.objects.filter(pk=self.owner.financial_profile.pk).delete()
        UserPreferences.objects.filter(pk=self.owner.preferences.pk).delete()
        body, _schema = self.export_response()
        self.assertIsNone(body["preferences"])
        self.assertIsNone(body["financialProfile"])
        self.assertEqual(len(body["accounts"]), 1)

    def test_subscription_create_schema_names_the_actual_detail_response(self):
        Subscription.objects.filter(user_account=self.owner.account).delete()
        configure_operator()
        open_offering(self.owner)
        open_to_investors(self.owner)
        eligible_subscriber(self.owner)
        response = self.client.post(
            "/api/v1/subscriptions/",
            {
                "offering": str(self.owner.offering.uuid),
                "userAccount": str(self.owner.account.uuid),
                "wallet": str(self.owner.wallet.uuid),
                "quantity": 10,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["quantity"], 10)
        self.assertEqual(body["amountDue"], "25.00")
        schema = self.response_schema("/api/v1/subscriptions/", "post", "201")
        self.assertEqual(set(schema["properties"]), set(body))
        self.assertTrue({"uuid", "status", "amountDue", "createdAt", "walletAddress"}.issubset(schema["required"]))

    def test_subscription_instruction_schema_accepts_the_existing_null_and_object_values(self):
        configure_operator(self.owner.refs.stablecoin)
        endpoint = f"/api/v1/subscriptions/{self.owner.subscription.uuid}/"
        draft = self.client.get(endpoint)
        self.assertEqual(draft.status_code, 200)
        self.assertIsNone(draft.json()["paymentInstruction"])
        for rail in ("bank_transfer", "stablecoin"):
            with self.subTest(rail=rail):
                Subscription.objects.filter(pk=self.owner.subscription.pk).update(
                    status="awaiting_payment",
                    reference="SCHEMA1234",
                    settlement_rail=rail,
                    settlement_asset=self.owner.refs.stablecoin if rail == "stablecoin" else None,
                )
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 200)
                instruction = response.json()["paymentInstruction"]
                self.assertEqual(instruction["rail"], rail)
                self.assertEqual(instruction["reference"], "SCHEMA1234")
                if rail == "stablecoin":
                    self.assertEqual(instruction["contractAddress"], "0x" + "5" * 40)
                else:
                    self.assertEqual(instruction["bankBsb"], "062000")
                for path, method, code in (
                    ("/api/v1/subscriptions/", "post", "201"),
                    ("/api/v1/subscriptions/{uuid}/", "get", "200"),
                ):
                    properties = self.response_schema(path, method, code)["properties"]
                    self.assertIn("paymentInstruction", properties)
                    field = self.resolved(properties["paymentInstruction"])
                    self.assertEqual(field.get("type"), "object")
                    self.assertTrue(field.get("nullable"))

    def test_capital_increase_page_is_already_a_real_paginator(self):
        response = self.client.get("/api/v1/tokens/capital-increases/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        row = body["results"][0]
        self.assertEqual(row["uuid"], str(self.owner.capital_increase.uuid))
        self.assertNotIn("boardResolutionReference", row)
        self.assertNotIn("page", body)
        schema = self.response_schema("/api/v1/tokens/capital-increases/")
        self.assertEqual(set(schema["properties"]), set(body))
        self.assertEqual(set(self.resolved(schema["properties"]["results"]["items"])["properties"]), set(row))

    def test_prepared_transfer_declares_the_real_token_and_transaction_fields(self):
        service = object.__new__(TokenTransferService)
        service.validate_transfer = Mock()
        chain = Mock(chain_id=84532, gas_price=100)
        chain.to_checksum_address.side_effect = lambda value: value
        chain.get_nonce.return_value = 3
        chain.estimate_gas.return_value = 65000
        chain.load_contract.return_value.functions.transfer.return_value._encode_transaction_data.return_value = (
            "0x1234"
        )
        service.chain_client = chain
        with patch("tokens.views.trading_transfer.TokenTransferService", side_effect=lambda: service) as constructor:
            constructor.contract_address = TokenTransferService.contract_address
            response = self.client.post(
                "/api/v1/trading/transfers/prepare/",
                {
                    "token": str(self.owner.deployed_token.uuid),
                    "fromAddress": self.owner.wallet.address,
                    "toAddress": self.other.wallet.address,
                    "amount": 12,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["amount"], 12)
        self.assertEqual(set(body["token"]), {"uuid", "symbol", "contractAddress"})
        schema = self.assert_fields(
            self.response_schema("/api/v1/trading/transfers/prepare/", "post"),
            body,
            {
                "token": "object",
                "fromAddress": "string",
                "toAddress": "string",
                "amount": "integer",
                "transactionData": "object",
            },
        )
        self.assert_fields(
            schema["properties"]["token"],
            body["token"],
            {"uuid": "string", "symbol": "string", "contractAddress": "string"},
        )
        self.assert_fields(
            schema["properties"]["transactionData"],
            body["transactionData"],
            {
                "to": "string",
                "data": "string",
                "value": "integer",
                "nonce": "integer",
                "chainId": "integer",
                "gasPrice": "integer",
                "gas": "integer",
            },
        )
        self.assertEqual(
            set(self.resolved(schema["properties"]["transactionData"])["required"]), set(body["transactionData"])
        )

    def test_broadcast_receipt_declares_existing_fields_and_nullable_absence(self):
        Wallet.objects.create(
            user_account=self.owner.account, address=SIGNER.address, chain="base", verification_status="VERIFIED"
        )
        signed_transaction = sign_legacy(to="0x" + "8" * 40)
        for receipt in ({"blockNumber": 7, "gasUsed": 21000}, {}):
            with self.subTest(receipt=receipt):
                with patch("tokens.views.trading_transfer.TokenTransferService") as constructor:
                    constructor.return_value.broadcast_transfer.return_value = ("0x" + "f" * 64, receipt)
                    response = self.client.post(
                        "/api/v1/trading/transfers/broadcast/", {"signedTransaction": signed_transaction}, format="json"
                    )
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(
                    body,
                    {
                        "txHash": "0x" + "f" * 64,
                        "blockNumber": receipt.get("blockNumber"),
                        "gasUsed": receipt.get("gasUsed"),
                    },
                )
                self.assert_fields(
                    self.response_schema("/api/v1/trading/transfers/broadcast/", "post"),
                    body,
                    {"txHash": "string", "blockNumber": "integer", "gasUsed": "integer"},
                )

    def test_provider_webhooks_remain_excluded(self):
        paths = set(self.document["paths"])
        for name in ("alchemy-webhook", "kycaid-webhook", "sumsub-webhook", "kycaid-crypto-webhook"):
            path = reverse(name)
            self.assertEqual(resolve(path).url_name, name)
            self.assertNotIn(path, paths)
        self.assertIn("/api/v1/trading/events/stream/", paths)
