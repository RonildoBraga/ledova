from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

from django.core.cache import cache
from django.db import connections
from eth_account import Account

from feature_flags.models import FeatureFlag
from shared.db import acting_for, current_alias, use_operator
from shared.tests.tenants import make_tenant
from shared.utils.typed_data import signable_message
from tokens.models import OrderActionSubmission, SigningChallenge, TransferOrder
from wallets.models import Wallet

OWNER = Account.from_key("0x" + "81" * 32)
OTHER_KEY = Account.from_key("0x" + "82" * 32)
BASE = "/api/v1/trading/orders/"


class ActionFixtures:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        with use_operator():
            FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
            self.tenant = make_tenant("order-action")
            self.wallet = Wallet.objects.create(user_account=self.tenant.account, address=OWNER.address, chain="base")
            self.order = TransferOrder.objects.create(
                token=self.tenant.deployed_token,
                payment_asset=self.tenant.refs.stablecoin,
                wallet=self.wallet,
                owner_account=self.tenant.account,
                wallet_address=self.wallet.address,
                order_type="buy",
                quantity=10,
                min_quantity=0,
                price_per_share=Decimal("2.50"),
            )
        self.client.force_authenticate(self.tenant.user)
        self.action_id = uuid4()
        self.events = []
        self.provider_states = []
        self.balance = Mock()
        self.balance.get_token_balance.side_effect = self.provider_balance
        self.patch("tokens.services.order_modification_service.ShareTokenService", return_value=self.balance)
        self.patch("tokens.events._publish", side_effect=lambda event, payload: self.events.append((event, payload)))
        self.patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)

    def patch(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def provider_balance(self, *args):
        self.provider_states.append(connections[current_alias()].in_atomic_block)
        return 100

    def identity(self, **changes):
        body = {"action_id": str(self.action_id), "owner_account_uuid": str(self.tenant.account.pk)}
        body.update(changes)
        return body

    def message(self, purpose="cancel", body=None, order=None):
        body = self.identity() if body is None else body
        return self.client.post(f"{BASE}{(order or self.order).pk}/{purpose}/message/", body, format="json")

    def modify_body(self, **changes):
        body = {
            **self.identity(),
            "new_quantity": "12",
            "new_min_quantity": "1",
            "new_price_per_share": "3.00",
        }
        body.update(changes)
        return body

    def sign(self, snapshot, signer=OWNER):
        challenge = snapshot["challenge"]
        return {
            "action_id": snapshot["actionId"],
            "owner_account_uuid": snapshot["ownerAccountUuid"],
            "digest": challenge["digest"],
            "signature": signer.sign_message(
                signable_message(challenge["domain"], challenge["types"], challenge["message"])
            ).signature.to_0x_hex(),
        }

    def signed(self, purpose="cancel", body=None):
        response = self.message(purpose, body)
        self.assertEqual(response.status_code, 200, response.content)
        return self.sign(response.json())

    def execute(self, purpose, body, order=None):
        return self.client.post(f"{BASE}{(order or self.order).pk}/{purpose}/", body, format="json")

    def recover(self, action_id=None, account_id=None):
        return self.client.get(
            f"{BASE}actions/{action_id or self.action_id}/",
            {"owner_account_uuid": str(account_id or self.tenant.account.pk)},
        )

    def context(self, order=None, account_id=None):
        return self.client.get(
            f"{BASE}{(order or self.order).pk}/action-context/",
            {"owner_account_uuid": str(account_id or self.tenant.account.pk)},
        )

    def journal(self, action_id=None):
        with use_operator():
            return OrderActionSubmission.objects.get(
                owner_account=self.tenant.account, action_id=action_id or self.action_id
            )

    def assert_pending(self, signed):
        self.assertEqual(self.journal(signed["action_id"]).status, "pending")
        with use_operator():
            self.assertFalse(SigningChallenge.objects.get(digest=signed["digest"]).is_consumed)
        self.assertEqual(self.events, [])


def cancel_message_for_order(actor, order):
    from tokens.services.order_actions import issue_order_action

    with acting_for(actor.pk):
        return issue_order_action(
            actor,
            order.pk,
            "cancel",
            {
                "action_id": uuid4(),
                "owner_account_uuid": order.owner_account_id,
            },
        ).challenge


def cancel_for_order(actor, order, digest, signature):
    from tokens.exceptions import OrderCancellationException
    from tokens.services.order_actions import execute_order_action

    with acting_for(actor.pk):
        challenge = SigningChallenge.objects.select_related("action").get(digest=digest)
        result = execute_order_action(
            actor,
            order.pk,
            "cancel",
            {
                "action_id": challenge.action.action_id,
                "owner_account_uuid": challenge.action.owner_account_id,
            },
            {"digest": digest, "signature": signature},
        )
    if result.action.status == "refused":
        raise OrderCancellationException(result.action.refusal_detail)
    return result.action.order


def legacy_action_values(order, signer, purpose, nonce, consumed=False):
    from copy import deepcopy

    from django.conf import settings
    from django.utils import timezone

    from shared.utils.typed_data import build_domain, typed_data_digest
    from tokens.services.signing_challenge import CHALLENGE_TYPES

    primary = "OrderCancel" if purpose == "cancel" else "OrderModify"
    fields = deepcopy(CHALLENGE_TYPES["order_" + purpose][primary + "V1"])
    types = {
        primary: [
            field
            for field in fields
            if field["name"]
            not in {
                "actionId",
                "protocolVersion",
                "ownerAccountUuid",
                "walletUuid",
                "tokenUuid",
            }
        ]
    }
    expires = timezone.now() + timezone.timedelta(minutes=5)
    domain = build_domain(settings.BLOCKCHAIN_CHAIN_ID, order.token.contract_address)
    message = {
        "orderUuid": str(order.pk),
        "wallet": signer.address,
        "nonce": str(nonce),
        "deadline": str(int(expires.timestamp())),
    }
    if purpose == "modify":
        message.update(newQuantity="12", newMinQuantity="0", newPricePerShare="3.00")
    signature = signer.sign_message(signable_message(domain, types, message)).signature.to_0x_hex()
    return {
        "purpose": "order_" + purpose,
        "order_id": order.pk,
        "wallet_id": order.wallet_id,
        "wallet_address": signer.address,
        "chain_id": domain["chainId"],
        "verifying_contract": domain["verifyingContract"],
        "payload": {"domain": domain, "types": types, "message": message},
        "digest": typed_data_digest(domain, types, message),
        "nonce": nonce,
        "expires_at": expires,
        "consumed_at": timezone.now() if consumed else None,
        "consumed_signature": signature if consumed else "",
    }, signature
