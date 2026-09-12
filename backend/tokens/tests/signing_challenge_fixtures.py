from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.utils import timezone
from eth_utils import to_checksum_address

from shared.utils.typed_data import build_domain, typed_data_digest
from tokens.models import OrderActionSubmission, SigningChallengePurpose


def pending_action(tenant, purpose="cancel", order=None, **changes):
    order = order or tenant.order
    values = {
        "action_id": uuid4(),
        "purpose": purpose,
        "owner_account_id": order.owner_account_id,
        "order": order,
        "wallet_id": order.wallet_id,
        "token": order.token,
        "initiated_by": tenant.user,
        "wallet_address": to_checksum_address(order.wallet_address),
        "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
        "verifying_contract": to_checksum_address(order.token.contract_address),
        "token_metadata": {"name": order.token.name, "symbol": order.token.symbol},
        "review_values": {
            "order_type": order.order_type,
            "quantity": str(order.quantity),
            "min_quantity": str(order.min_quantity),
            "price_per_share": str(order.price_per_share),
            "filled_quantity": str(order.filled_quantity),
            "remaining_quantity": str(order.remaining_quantity),
            "status": order.status,
            "modification_count": order.modification_count,
            "can_cancel": order.can_cancel,
            "can_modify": order.can_be_modified,
        },
    }
    if purpose == "modify":
        values.update(new_quantity=12, new_min_quantity=0, new_price_per_share=Decimal("3.00"))
    values.update(changes)
    return OrderActionSubmission.objects.create(**values)


def action_fields(action):
    fields = {
        "actionId": str(action.action_id),
        "protocolVersion": action.protocol_version,
        "ownerAccountUuid": str(action.owner_account_id),
        "walletUuid": str(action.wallet_id),
        "tokenUuid": str(action.token_id),
        "orderUuid": str(action.order_id),
    }
    if action.purpose == "modify":
        fields.update(
            newQuantity=action.new_quantity,
            newMinQuantity=action.new_min_quantity,
            newPricePerShare=str(action.new_price_per_share),
        )
    return fields


def historical_cancel_values(order, nonce=11):
    types = {
        "OrderCancel": [
            {"name": "orderUuid", "type": "string"},
            {"name": "wallet", "type": "address"},
            {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ]
    }
    expires = timezone.now() + timezone.timedelta(seconds=settings.SIGNING_CHALLENGE_TTL_SECONDS)
    domain = build_domain(settings.BLOCKCHAIN_CHAIN_ID, None)
    wallet_address = to_checksum_address(order.wallet_address)
    message = {
        "orderUuid": str(order.pk),
        "wallet": wallet_address,
        "nonce": str(nonce),
        "deadline": str(int(expires.timestamp())),
    }
    return {
        "purpose": SigningChallengePurpose.ORDER_CANCEL,
        "order_id": order.pk,
        "wallet_id": order.wallet_id,
        "wallet_address": wallet_address,
        "chain_id": domain["chainId"],
        "verifying_contract": domain["verifyingContract"],
        "payload": {"domain": domain, "types": types, "message": message},
        "digest": typed_data_digest(domain, types, message),
        "nonce": nonce,
        "expires_at": expires,
    }
