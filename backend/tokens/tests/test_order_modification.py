from decimal import Decimal
from unittest.mock import patch

from eth_account import Account
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from shared.tests.tenants import make_tenant
from shared.utils.typed_data import signable_message
from tokens.exceptions import ChallengeAlreadyUsedException
from tokens.models import OrderModificationLog, TransferOrder
from tokens.models.choices import TransferOrderStatus, TransferOrderType
from tokens.services import OrderModificationService
from wallets.models import Wallet

OWNER = Account.from_key("0x" + "63" * 32)
SIGNATURE = "0x" + "ab" * 65


class OrderModificationTest(APITestCase):
    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.tenant = make_tenant("alice")
        self.signing_wallet = Wallet.objects.create(
            user_account=self.tenant.account,
            address=OWNER.address,
            chain="base",
            verification_status="VERIFIED",
        )
        self.order = TransferOrder.objects.create(
            order_type=TransferOrderType.BUY,
            token=self.tenant.deployed_token,
            payment_asset=self.tenant.refs.stablecoin,
            wallet=self.signing_wallet,
            owner_account=self.tenant.account,
            wallet_address=OWNER.address,
            quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def _challenge(self, price="2.00", quantity=12):
        return OrderModificationService().generate_modification_message(
            order=self.order, new_quantity=quantity, new_min_quantity=0, new_price=Decimal(price)
        )

    @staticmethod
    def _sign(issued):
        return OWNER.sign_message(
            signable_message(issued["domain"], issued["types"], issued["message"])
        ).signature.hex()

    @patch("tokens.events.publish_trading_event")
    def test_apply_modification_bulk_writes_one_log_row_per_changed_field(self, publish):
        issued = self._challenge()
        signature = self._sign(issued)

        order, changes = OrderModificationService().apply_modification(
            order=self.order,
            digest=issued["digest"],
            signature=signature,
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
            self.assertEqual((log.signer_address, log.ip_address), (order.wallet_address, "1.2.3.4"))
            self.assertEqual(log.challenge.digest, issued["digest"])
            self.assertEqual(len(log.user_agent), 500)
        self.assertEqual((logs["quantity"].old_value, logs["quantity"].new_value), ("10", "12"))
        publish.assert_called_once_with("order_modified", str(order.token.uuid))

    def test_a_modify_signature_cannot_be_replayed(self):
        issued = self._challenge()
        signature = self._sign(issued)
        OrderModificationService().apply_modification(order=self.order, digest=issued["digest"], signature=signature)

        with self.assertRaises(ChallengeAlreadyUsedException):
            OrderModificationService().apply_modification(
                order=self.order, digest=issued["digest"], signature=signature
            )

        self.assertEqual(OrderModificationLog.objects.filter(field_name="quantity").count(), 1)

    def test_the_service_reads_the_new_values_from_the_payload_it_stored(self):
        issued = self._challenge(price="2.00", quantity=12)

        order, _ = OrderModificationService().apply_modification(
            order=self.order, digest=issued["digest"], signature=self._sign(issued)
        )

        self.assertEqual((order.quantity, order.price_per_share), (12, Decimal("2.00")))
        self.assertEqual(issued["message"]["newQuantity"], "12")
        self.assertEqual(issued["message"]["newPricePerShare"], "2.00")

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_service_errors_reach_the_client_unwrapped(self, _throttle):
        self.client.force_authenticate(self.tenant.user)
        TransferOrder.objects.filter(pk=self.order.pk).update(status=TransferOrderStatus.CANCELLED)

        response = self.client.post(
            f"/api/v1/trading/orders/{self.order.uuid}/modify/message/", {"newQuantity": 5}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Order with status 'Cancelled' cannot be modified.")

    @patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
    def test_pending_swap_conflicts_before_the_status_check(self, _throttle):
        self.client.force_authenticate(self.tenant.user)
        TransferOrder.objects.filter(pk=self.tenant.order.pk).update(
            status=TransferOrderStatus.PARTIALLY_FILLED, filled_quantity=4
        )

        response = self.client.post(
            f"/api/v1/trading/orders/{self.tenant.order.uuid}/modify/message/", {"newQuantity": 12}, format="json"
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "Cannot modify order with pending swap. Complete or cancel the swap first."
        )
