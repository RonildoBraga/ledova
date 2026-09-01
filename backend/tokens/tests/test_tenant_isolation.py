"""Two-tenant cross-access tests for trading orders (deferred-hardening #1).

Regression net for the confirmed CRITICAL/HIGH IDORs on the trading order
endpoints: a tenant must never read another tenant's order — by list, by UUID
retrieve, or via a detail @action.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from companies.models import Company
from feature_flags.models import FeatureFlag
from tokens.models import ShareToken, TransferOrder
from tokens.models.choices import ShareTokenStatus, ShareTokenType, TransferOrderStatus, TransferOrderType
from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()


class TenantOrderIsolationTest(APITestCase):
    def _make_tenant(self, email, address):
        user = User.objects.create_user(email=email, password="pw-12345678")
        user.is_active = True
        user.is_email_verified = True
        user.save()
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account,
            address=address,
            chain="ethereum",
            custody_model="non_custodial",
            wallet_type="software",
            verification_status="PENDING",
        )
        return user, account, wallet

    def _make_order(self, wallet):
        company = Company.objects.create(
            owner=User.objects.create_user(email=f"owner-{wallet.address}@ex.com", password="pw-12345678"),
            name="Acme Pty Ltd",
            company_type="private",
            acn=str(abs(hash(wallet.address)) % 10**9).zfill(9),
            status="active",
        )
        token = ShareToken.objects.create(
            company=company,
            name="Acme Ordinary",
            symbol="ACME",
            token_type=ShareTokenType.ORDINARY,
            total_supply="1000000",
            status=ShareTokenStatus.DEPLOYED,
            deployment_tx_hash="0x" + "0" * 64,
        )
        return TransferOrder.objects.create(
            token=token,
            order_type=TransferOrderType.SELL,
            status=TransferOrderStatus.OPEN,
            wallet_address=wallet.address,
            quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def setUp(self):
        FeatureFlag.objects.create(name="trading_enabled", enabled=True)
        self.alice, _, alice_wallet = self._make_tenant("alice@ex.com", "0x" + "a" * 40)
        self.bob, _, bob_wallet = self._make_tenant("bob@ex.com", "0x" + "b" * 40)
        self.alice_order = self._make_order(alice_wallet)
        self.bob_order = self._make_order(bob_wallet)

    def test_queryset_scoping_excludes_other_tenant(self):
        visible = TransferOrder.objects.visible_to_user(self.bob)
        uuids = set(visible.values_list("uuid", flat=True))
        self.assertIn(self.bob_order.uuid, uuids)
        self.assertNotIn(self.alice_order.uuid, uuids)

    def test_retrieve_other_tenant_order_is_404(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.get(f"/api/v1/trading/orders/{self.alice_order.uuid}/")
        self.assertEqual(resp.status_code, 404)

    def test_retrieve_own_order_succeeds(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.get(f"/api/v1/trading/orders/{self.bob_order.uuid}/")
        self.assertEqual(resp.status_code, 200)

    def test_list_returns_only_own_orders(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.get("/api/v1/trading/orders/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body["results"] if isinstance(body, dict) and "results" in body else body
        returned = {r.get("uuid") for r in rows}
        self.assertNotIn(str(self.alice_order.uuid), returned)

    def test_detail_action_on_other_tenant_order_is_404(self):
        self.client.force_authenticate(self.bob)
        resp = self.client.get(f"/api/v1/trading/orders/{self.alice_order.uuid}/modifications/")
        self.assertEqual(resp.status_code, 404)
