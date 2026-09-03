"""Signed order modifications write one audit row per changed field and surface service errors as-is."""

from decimal import Decimal
from unittest.mock import patch

from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from shared.tests.tenants import make_tenant
from shared.utils.signature import generate_order_modify_message
from tokens.exceptions import OrderModificationException
from tokens.models import OrderModificationLog, TransferOrder
from tokens.models.choices import TransferOrderType
from tokens.services import OrderModificationService

SIGNATURE = "0x" + "ab" * 65


class OrderModificationTest(APITestCase):
    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.tenant = make_tenant("alice")
        self.order = TransferOrder.objects.create(
            order_type=TransferOrderType.BUY,
            token=self.tenant.deployed_token,
            payment_token=self.tenant.refs.stablecoin,
            wallet=self.tenant.wallet,
            owner_account=self.tenant.account,
            wallet_address=self.tenant.wallet.address,
            quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def _message(self, price="2.00"):
        return generate_order_modify_message(
            order_uuid=str(self.order.uuid),
            token_symbol=self.order.token.symbol,
            order_type="BUY",
            new_quantity=12,
            new_min_quantity=0,
            new_price_per_share=price,
            wallet_address=self.order.wallet_address,
            nonce=1,
        )

    @patch("tokens.events.publish_trading_event")
    @patch("tokens.services.order_modification_service.recover_address_from_signature")
    def test_apply_modification_bulk_writes_one_log_row_per_changed_field(self, recover, publish):
        recover.return_value = self.order.wallet_address

        order, changes = OrderModificationService().apply_modification(
            order=self.order,
            message=self._message(),
            signature=SIGNATURE,
            ip_address="1.2.3.4",
            user_agent="agent " * 200,
        )

        self.assertEqual((order.quantity, order.price_per_share, order.modification_count), (12, Decimal("2.00"), 1))
        self.assertEqual(
            changes,
            [
                {"field": "quantity", "old": "10", "new": "12"},
                {"field": "price_per_share", "old": "1.50", "new": "2.00"},
            ],
        )
        logs = {log.field_name: log for log in OrderModificationLog.objects.filter(order=order)}
        self.assertEqual(set(logs), {"quantity", "price_per_share"})
        for log in logs.values():
            self.assertEqual(
                (log.signer_address, log.ip_address, log.signature), (order.wallet_address, "1.2.3.4", SIGNATURE)
            )
            self.assertEqual(log.modification_message, self._message())
            self.assertEqual(len(log.user_agent), 500)
        self.assertEqual((logs["quantity"].old_value, logs["quantity"].new_value), ("10", "12"))
        publish.assert_called_once_with("order_modified", str(order.token.uuid))

    @patch("tokens.services.order_modification_service.recover_address_from_signature")
    def test_malformed_price_is_a_modification_error(self, recover):
        recover.return_value = self.order.wallet_address

        with self.assertRaises(OrderModificationException) as ctx:
            OrderModificationService().apply_modification(
                order=self.order, message=self._message(price="two"), signature=SIGNATURE
            )
        self.assertTrue(str(ctx.exception.detail).startswith("Invalid message format"))
        self.assertFalse(OrderModificationLog.objects.exists())

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_service_errors_reach_the_client_unwrapped(self, _throttle):
        self.client.force_authenticate(self.tenant.user)

        response = self.client.post(
            f"/api/v1/trading/orders/{self.tenant.order.uuid}/modify/message/", {"newQuantity": 5}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Order with status 'Open' cannot be modified.")
