from decimal import Decimal
from uuid import uuid4

from rest_framework.test import APITransactionTestCase

from tokens.models import OrderModificationLog, TransferOrder
from tokens.models.choices import TransferOrderStatus
from tokens.tests.order_action_fixtures import BASE, ActionFixtures


class OrderModificationTest(ActionFixtures, APITransactionTestCase):
    def _challenge(self, price="3.00", quantity=12):
        response = self.message(
            "modify", self.modify_body(new_quantity=str(quantity), new_min_quantity="0", new_price_per_share=price)
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_apply_modification_bulk_writes_one_log_row_per_changed_field(self):
        issued = self._challenge()
        response = self.client.post(
            f"{BASE}{self.order.pk}/modify/",
            self.sign(issued),
            format="json",
            REMOTE_ADDR="1.2.3.4",
            HTTP_USER_AGENT="agent " * 200,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.order.refresh_from_db()
        self.assertEqual(
            (self.order.quantity, self.order.price_per_share, self.order.modification_count), (12, Decimal("3.00"), 1)
        )
        self.assertEqual(
            response.json()["result"]["changes"],
            [
                {"field": "quantity", "old": "10", "new": "12"},
                {"field": "price_per_share", "old": "2.50", "new": "3.00"},
            ],
        )
        logs = {log.field_name: log for log in OrderModificationLog.objects.filter(order=self.order)}
        self.assertEqual(set(logs), {"quantity", "price_per_share"})
        for log in logs.values():
            self.assertEqual((log.signer_address, log.ip_address), (self.order.wallet_address, "1.2.3.4"))
            self.assertEqual(log.challenge.digest, issued["challenge"]["digest"])
            self.assertEqual(len(log.user_agent), 500)
        self.assertEqual((logs["quantity"].old_value, logs["quantity"].new_value), ("10", "12"))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0][0], "order_modified")

    def test_a_modify_signature_cannot_apply_another_modification_on_replay(self):
        issued = self._challenge()
        first = self.execute("modify", self.sign(issued))
        self.assertEqual(first.status_code, 200)
        replay = self.execute("modify", self.sign(issued))
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["result"], first.json()["result"])
        self.assertEqual(OrderModificationLog.objects.filter(field_name="quantity").count(), 1)
        self.action_id = uuid4()
        second = self._challenge(quantity=13)
        self.assertEqual(self.execute("modify", {**self.sign(issued), **self.identity()}).status_code, 400)
        self.assertEqual(self.execute("modify", self.sign(second)).status_code, 200)
        self.assertEqual(OrderModificationLog.objects.filter(field_name="quantity").count(), 2)

    def test_the_service_reads_the_new_values_from_the_payload_it_stored(self):
        issued = self._challenge(price="3.00", quantity=12)
        response = self.execute("modify", {**self.sign(issued), "new_quantity": "1", "new_price_per_share": "0.01"})
        self.assertEqual(response.status_code, 200, response.content)
        self.order.refresh_from_db()
        self.assertEqual((self.order.quantity, self.order.price_per_share), (12, Decimal("3.00")))
        self.assertEqual(issued["challenge"]["message"]["newQuantity"], "12")
        self.assertEqual(issued["challenge"]["message"]["newPricePerShare"], "3.00")

    def test_service_errors_reach_the_client_unwrapped(self):
        TransferOrder.objects.filter(pk=self.order.pk).update(status=TransferOrderStatus.CANCELLED)
        response = self.message("modify", self.modify_body())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Order with status 'Cancelled' cannot be modified.")
        self.assertEqual(self.journal().status, "pending")

    def test_pending_swap_conflicts_before_the_status_check(self):
        TransferOrder.objects.filter(pk=self.tenant.order.pk).update(
            status=TransferOrderStatus.PARTIALLY_FILLED, filled_quantity=4
        )
        response = self.message("modify", self.modify_body(), order=self.tenant.order)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "Cannot modify order with pending swap. Complete or cancel the swap first."
        )
        self.assertEqual(self.journal().status, "pending")
