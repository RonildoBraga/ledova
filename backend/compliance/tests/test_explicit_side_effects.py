from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from compliance.constants import (
    ASSESSMENT_STATUS_PENDING,
    RULE_TYPE_RAPID_TRANSACTIONS,
    TRANSACTION_MONITORING_WINDOW_HOURS,
)
from compliance.models import ComplianceAlert, CustomerRiskAssessment, MonitoringRule
from compliance.services.transaction_monitoring import TransactionMonitoringService
from users.models import UserAccount, UserProfile
from users.services.setup import ensure_defaults
from wallets.models import Transaction, Wallet
from wallets.services import WalletSyncService
from wallets.services.transaction_confirmation import TransactionConfirmationService

User = get_user_model()

CHECK = "compliance.services.transaction_monitoring.TransactionMonitoringService.check_transaction"


def tx_payload(tx_hash, block_timestamp):
    return {
        "tx_hash": tx_hash,
        "from_address": "0x" + "d" * 40,
        "to_address": "0x" + "c" * 40,
        "amount": "1.5",
        "asset_symbol": "ETH",
        "block_timestamp": block_timestamp,
    }


class TransactionMonitoringOnCreateTest(TestCase):
    def setUp(self):
        self.account = UserAccount.objects.create(account_number="MON-ACC")
        self.wallet = Wallet.objects.create(
            user_account=self.account,
            address="0x" + "c" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )

    def sync(self, *payloads):
        client = MagicMock()
        client.get_transaction_history.return_value = list(payloads)
        with patch("wallets.services.sync.get_blockchain_client", return_value=client):
            return WalletSyncService.sync_wallet(self.wallet)

    def test_sync_screens_each_newly_created_transaction_once(self):
        with patch(CHECK, return_value=[]) as check:
            self.assertEqual(self.sync(tx_payload("0xnew", timezone.now()))["transactions"], 1)
            self.assertEqual(self.sync(tx_payload("0xnew", timezone.now()))["transactions"], 0)

        check.assert_called_once()
        tx = Transaction.objects.get(tx_hash="0xnew")
        self.assertEqual(check.call_args.kwargs, {"transaction": tx, "user_account": self.account})

    def test_sync_skips_screening_for_transactions_older_than_the_window(self):
        old = timezone.now() - timedelta(hours=TRANSACTION_MONITORING_WINDOW_HOURS, minutes=1)
        with patch(CHECK, return_value=[]) as check:
            self.assertEqual(self.sync(tx_payload("0xold", old))["transactions"], 1)
        check.assert_not_called()

    def test_monitoring_failure_does_not_roll_back_the_sync(self):
        with patch(CHECK, side_effect=RuntimeError("screening down")):
            result = self.sync(tx_payload("0xboom", timezone.now()))

        self.assertEqual(result["status"], "success")
        self.assertTrue(Transaction.objects.filter(tx_hash="0xboom", wallet=self.wallet).exists())

    def test_monitoring_failure_does_not_roll_back_a_pending_transfer(self):
        with patch(CHECK, side_effect=RuntimeError("screening down")) as check:
            result = TransactionConfirmationService.create_pending_transaction(
                wallet=self.wallet, tx_hash="0xpending", to_address="0x" + "e" * 40, amount=Decimal("0.5")
            )

        self.assertEqual(result["status"], "pending")
        tx = Transaction.objects.get(tx_hash="0xpending")
        self.assertEqual(check.call_args.kwargs, {"transaction": tx, "user_account": self.account})

    def test_active_rule_creates_an_alert_for_the_new_transaction(self):
        rule = MonitoringRule.objects.create(
            rule_code="MON-002",
            name="Rapid",
            description="More than one transaction per hour",
            rule_type=RULE_TYPE_RAPID_TRANSACTIONS,
            parameters={"max_transactions": 1, "period_minutes": 60},
        )

        self.assertEqual(self.sync(tx_payload("0xrapid", timezone.now()))["transactions"], 1)

        alert = ComplianceAlert.objects.get(monitoring_rule=rule)
        self.assertEqual(alert.transaction, Transaction.objects.get(tx_hash="0xrapid"))
        self.assertEqual(alert.user_account, self.account)

    def test_check_new_transaction_swallows_errors(self):
        tx = Transaction.objects.create(
            tx_hash="0xdirect",
            chain="ethereum",
            from_address=self.wallet.address,
            to_address="0x" + "e" * 40,
            asset=Transaction._meta.get_field("asset").related_model.objects.create(symbol="ETH", name="Ether"),
            amount=Decimal("1"),
            wallet=self.wallet,
        )
        with patch(CHECK, side_effect=RuntimeError("boom")):
            self.assertIsNone(TransactionMonitoringService.check_new_transaction(tx))


class PendingRiskAssessmentOnAccountCreateTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="assess@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.user)

    def pending_for(self, account):
        return CustomerRiskAssessment.objects.filter(user_account=account, assessment_status=ASSESSMENT_STATUS_PENDING)

    def test_ensure_defaults_creates_one_pending_assessment_for_a_new_account(self):
        _, account, _, _ = ensure_defaults(self.user)
        ensure_defaults(self.user)

        self.assertEqual(self.pending_for(account).count(), 1)

    def test_api_account_creation_creates_a_pending_assessment(self):
        self.client.force_authenticate(self.user)

        response = self.client.post("/api/user-accounts/", {"accountType": "individual"}, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        account = UserAccount.objects.get(uuid=response.json()["uuid"])
        self.assertEqual(self.pending_for(account).count(), 1)
