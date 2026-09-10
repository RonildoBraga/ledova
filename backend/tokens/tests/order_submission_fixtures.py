from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.test import override_settings
from eth_account import Account
from web3 import Web3

from feature_flags.models import FeatureFlag
from shared.db import current_alias, use_operator
from shared.tests.tenants import make_tenant
from shared.utils.typed_data import signable_message
from tokens.models import (
    OrderSubmission,
    SigningChallenge,
    TransferOrder,
    TransferOrderStatus,
)
from wallets.models import Wallet

OWNER = Account.from_key("0x" + "71" * 32)
COUNTERPARTY = Account.from_key("0x" + "72" * 32)
OTHER_KEY = Account.from_key("0x" + "73" * 32)
BASE = "/api/v1/trading/orders/"
CONTRACT = "0x" + "9d" * 20


def chain_client():
    client = Mock(chain_id=settings.BLOCKCHAIN_CHAIN_ID)
    client.is_valid_address.side_effect = Web3.is_address
    client.to_checksum_address.side_effect = Web3.to_checksum_address
    client.send_raw_transaction.side_effect = AssertionError("An order submission must not broadcast")
    return client


def pending_submission(tenant, wallet=None, **changes):
    wallet = wallet or tenant.wallet
    values = {
        "submission_id": uuid4(),
        "owner_account": wallet.user_account,
        "wallet": wallet,
        "token": tenant.deployed_token,
        "initiated_by": tenant.user,
        "wallet_address": Web3.to_checksum_address(wallet.address),
        "order_type": "buy",
        "quantity": 10,
        "min_quantity": 0,
        "price_per_share": Decimal("2.50"),
        "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
        "verifying_contract": tenant.deployed_token.contract_address,
        "token_metadata": {"name": tenant.deployed_token.name, "symbol": tenant.deployed_token.symbol},
    }
    values.update(changes)
    return OrderSubmission.objects.create(**values)


class SubmissionFixtures:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.settings_override = override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        with use_operator():
            FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
            self.tenant = make_tenant("submission")
            self.wallet = Wallet.objects.create(
                user_account=self.tenant.account, address=OWNER.address, chain="base", verification_status="VERIFIED"
            )
            TransferOrder.objects.filter(token=self.tenant.deployed_token).update(status=TransferOrderStatus.CANCELLED)
            self.initial_order_count = TransferOrder.objects.count()
        self.client.force_authenticate(self.tenant.user)
        self.submission_id = uuid4()
        self.chain = chain_client()
        self.whitelist = Mock()
        self.whitelist.is_whitelisted.return_value = True
        self.balance = Mock()
        self.balance.get_token_balance.return_value = 100
        self.events = []
        for target, replacement in (
            ("tokens.services.token_transfer_service.get_base_chain_client", self.chain),
            ("tokens.services.atomic_swap_service.get_base_chain_client", self.chain),
            ("tokens.services.token_transfer_service.WhitelistService", self.whitelist),
            ("tokens.services.atomic_swap_service.WhitelistService", self.whitelist),
            ("tokens.services.ShareTokenService", self.balance),
        ):
            self.patch(target, return_value=replacement)
        self.patch("tokens.events._publish", side_effect=self.published)
        self.patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)

    def patch(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def published(self, event, payload):
        self.events.append((event, payload, current_alias(), connections[current_alias()].in_atomic_block))

    def body(self, **changes):
        body = {
            "submission_id": str(self.submission_id),
            "owner_account_uuid": str(self.tenant.account.pk),
            "token": str(self.tenant.deployed_token.pk),
            "wallet_uuid": str(self.wallet.pk),
            "wallet_address": self.wallet.address,
            "order_type": "buy",
            "quantity": 10,
            "min_quantity": 0,
            "price_per_share": "2.50",
        }
        body.update(changes)
        return body

    def message(self, body=None):
        return self.client.post(f"{BASE}create/message/", body or self.body(), format="json")

    def issue(self, body=None):
        response = self.message(body)
        self.assertEqual(response.status_code, 200, response.content)
        snapshot = response.json()
        self.assertEqual(snapshot["status"], "pending")
        self.assertIsNotNone(snapshot["challenge"])
        return snapshot["challenge"]

    def signed_body(self, body=None, *, signer=OWNER):
        body = body or self.body()
        challenge = self.issue(body)
        signature = signer.sign_message(
            signable_message(challenge["domain"], challenge["types"], challenge["message"])
        ).signature.to_0x_hex()
        return {**body, "digest": challenge["digest"], "signature": signature}

    def create(self, signed):
        return self.client.post(f"{BASE}create/", signed, format="json")

    def recover(self, submission_id=None, account_id=None):
        return self.client.get(
            f"{BASE}submissions/{submission_id or self.submission_id}/",
            {"owner_account_uuid": str(account_id or self.tenant.account.pk)},
        )

    def submission(self, submission_id=None):
        with use_operator():
            return OrderSubmission.objects.get(
                owner_account=self.tenant.account, submission_id=submission_id or self.submission_id
            )

    def assert_pending_and_unspent(self, signed):
        self.assertEqual(self.submission(signed["submission_id"]).status, "pending")
        with use_operator():
            self.assertFalse(SigningChallenge.objects.get(digest=signed["digest"]).is_consumed)
            self.assertEqual(TransferOrder.objects.count(), self.initial_order_count)
        self.assertEqual(self.events, [])
        self.chain.send_raw_transaction.assert_not_called()

    def counter_order(self):
        with use_operator():
            wallet = Wallet.objects.create(
                user_account=self.tenant.account,
                address=COUNTERPARTY.address,
                chain="base",
                verification_status="VERIFIED",
            )
            order = TransferOrder.objects.create(
                token=self.tenant.deployed_token,
                payment_asset=self.tenant.refs.stablecoin,
                wallet=wallet,
                owner_account=self.tenant.account,
                wallet_address=wallet.address,
                order_type="sell",
                quantity=10,
                price_per_share=Decimal("2.50"),
            )
            self.initial_order_count += 1
            return order
