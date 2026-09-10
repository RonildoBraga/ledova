from copy import deepcopy

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from eth_account.messages import _hash_eip191_message, encode_typed_data
from rest_framework.exceptions import APIException
from web3 import Web3

from assets.models import Asset
from operators.exceptions import SettlementAssetNotDeployedException
from operators.settlement import require_deployment
from tokens.models import ShareToken

SETTLEMENT_PROTOCOL_VERSION = 1
SETTLEMENT_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "SwapOrder": [
        {"name": "seller", "type": "address"},
        {"name": "buyer", "type": "address"},
        {"name": "shareToken", "type": "address"},
        {"name": "paymentToken", "type": "address"},
        {"name": "shareAmount", "type": "uint256"},
        {"name": "paymentAmount", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
}


class SettlementContextChanged(APIException):
    status_code = 409
    default_detail = "The original swap context is no longer admitted. Review the recorded swap before continuing."
    default_code = "swap_settlement_context_changed"
    expose_code = True


class SettlementContextRequired(APIException):
    status_code = 400
    default_detail = "Refresh this swap and submit its exact settlement context."
    default_code = "swap_context_refresh_required"
    expose_code = True


class SettlementApprovalUncertain(Exception):
    def __init__(self, tx_hash):
        super().__init__("Approval outcome remains unconfirmed.")
        self.tx_hash = tx_hash


def settlement_address(value):
    if not Web3.is_address(value) or int(value, 16) == 0:
        raise SettlementContextChanged()
    return Web3.to_checksum_address(value)


def configured_domain():
    chain_id = settings.BLOCKCHAIN_CHAIN_ID
    if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
        raise SettlementContextChanged()
    return {
        "name": "LedovaAtomicSwap",
        "version": "1",
        "chainId": str(chain_id),
        "verifyingContract": settlement_address(settings.ATOMIC_SWAP_ADDRESS),
    }


def _party(order, address):
    return {
        "order_uuid": str(order.pk),
        "owner_account_uuid": str(order.owner_account_id),
        "wallet_uuid": str(order.wallet_id),
        "payment_asset_uuid": str(order.payment_asset_id) if order.payment_asset_id else None,
        "address": settlement_address(address),
    }


def capture_settlement_context(swap, price_per_share=None):
    token = swap.share_token
    payment = swap.payment_asset
    if (swap.buy_order.payment_asset_id or swap.sell_order.payment_asset_id) != payment.pk:
        raise SettlementContextChanged()
    for order, address, kind in (
        (swap.sell_order, swap.seller_address, "sell"),
        (swap.buy_order, swap.buyer_address, "buy"),
    ):
        if (
            order.token_id != token.pk
            or order.order_type != kind
            or order.owner_account_id != order.wallet.user_account_id
            or order.wallet_address.casefold() != address.casefold()
            or order.wallet.address.casefold() != address.casefold()
        ):
            raise SettlementContextChanged()
    deployment = require_deployment(payment)
    typed_data = {
        "types": deepcopy(SETTLEMENT_TYPES),
        "primaryType": "SwapOrder",
        "domain": configured_domain(),
        "message": {
            "seller": settlement_address(swap.seller_address),
            "buyer": settlement_address(swap.buyer_address),
            "shareToken": settlement_address(token.contract_address),
            "paymentToken": settlement_address(deployment.contract_address),
            "shareAmount": str(swap.share_amount),
            "paymentAmount": str(swap.payment_amount),
            "nonce": str(swap.nonce),
            "deadline": str(int(swap.expires_at.timestamp())),
        },
    }
    signable = encode_typed_data(full_message=typed_data)
    context = {
        "protocol_version": SETTLEMENT_PROTOCOL_VERSION,
        "swap_uuid": str(swap.pk),
        "seller": _party(swap.sell_order, swap.seller_address),
        "buyer": _party(swap.buy_order, swap.buyer_address),
        "share_token": {
            "uuid": str(token.pk),
            "address": typed_data["message"]["shareToken"],
            "chain": token.chain,
            "name": token.name,
            "symbol": token.symbol,
            "decimals": token.decimals,
        },
        "payment_asset": {
            "uuid": str(payment.pk),
            "name": payment.name,
            "symbol": payment.symbol,
            "pricing_decimals": payment.decimals,
            "deployment_uuid": str(deployment.pk),
            "deployment_chain": deployment.chain,
            "deployment_address": typed_data["message"]["paymentToken"],
            "deployment_decimals": deployment.decimals,
        },
        "price_per_share": str(price_per_share if price_per_share is not None else swap.sell_order.price_per_share),
        "typed_data": typed_data,
        "digest": "0x" + _hash_eip191_message(signable).hex(),
        "order_hash": signable.body.hex(),
    }
    swap.seller_wallet_id = swap.sell_order.wallet_id
    swap.buyer_wallet_id = swap.buy_order.wallet_id
    swap.settlement_protocol_version = SETTLEMENT_PROTOCOL_VERSION
    swap.settlement_context = context
    swap.settlement_digest = context["digest"]
    swap.order_hash = context["order_hash"]
    return context


def recorded_settlement_context(swap):
    context = swap.settlement_context
    try:
        typed = context["typed_data"]
        message = typed["message"]
        expected = (
            str(swap.pk),
            str(swap.sell_order_id),
            str(swap.buy_order_id),
            str(swap.seller_wallet_id),
            str(swap.buyer_wallet_id),
            str(swap.share_token_id),
            str(swap.payment_asset_id),
            settlement_address(swap.seller_address),
            settlement_address(swap.buyer_address),
            str(swap.share_amount),
            str(swap.payment_amount),
            str(swap.nonce),
            str(int(swap.expires_at.timestamp())),
        )
        actual = (
            context["swap_uuid"],
            context["seller"]["order_uuid"],
            context["buyer"]["order_uuid"],
            context["seller"]["wallet_uuid"],
            context["buyer"]["wallet_uuid"],
            context["share_token"]["uuid"],
            context["payment_asset"]["uuid"],
            message["seller"],
            message["buyer"],
            message["shareAmount"],
            message["paymentAmount"],
            message["nonce"],
            message["deadline"],
        )
        if (
            swap.settlement_protocol_version != SETTLEMENT_PROTOCOL_VERSION
            or context["protocol_version"] != SETTLEMENT_PROTOCOL_VERSION
            or expected != actual
            or typed["types"] != SETTLEMENT_TYPES
            or typed["primaryType"] != "SwapOrder"
            or typed["domain"]["name"] != "LedovaAtomicSwap"
            or typed["domain"]["version"] != "1"
            or set(typed["domain"]) != {"name", "version", "chainId", "verifyingContract"}
            or not isinstance(typed["domain"]["chainId"], str)
            or str(int(typed["domain"]["chainId"])) != typed["domain"]["chainId"]
            or int(typed["domain"]["chainId"]) <= 0
            or settlement_address(typed["domain"]["verifyingContract"]) != typed["domain"]["verifyingContract"]
            or context["seller"]["address"] != message["seller"]
            or context["buyer"]["address"] != message["buyer"]
            or context["share_token"]["address"] != message["shareToken"]
            or context["payment_asset"]["deployment_address"] != message["paymentToken"]
        ):
            raise SettlementContextChanged()
        signable = encode_typed_data(full_message=typed)
        if (
            context["digest"] != swap.settlement_digest
            or swap.settlement_digest != "0x" + _hash_eip191_message(signable).hex()
            or context["order_hash"] != swap.order_hash
            or swap.order_hash != signable.body.hex()
        ):
            raise SettlementContextChanged()
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SettlementContextChanged() from exc
    return deepcopy(context)


def assert_current_settlement(swap):
    context = recorded_settlement_context(swap)
    try:
        token = ShareToken.objects.get(pk=swap.share_token_id)
        payment = Asset.objects.get(pk=swap.payment_asset_id)
        deployment = require_deployment(payment)
        current = (
            configured_domain(),
            settlement_address(token.contract_address),
            token.chain,
            token.decimals,
            str(deployment.pk),
            deployment.chain,
            settlement_address(deployment.contract_address),
            deployment.decimals,
            payment.decimals,
        )
        original = (
            context["typed_data"]["domain"],
            context["share_token"]["address"],
            context["share_token"]["chain"],
            context["share_token"]["decimals"],
            context["payment_asset"]["deployment_uuid"],
            context["payment_asset"]["deployment_chain"],
            context["payment_asset"]["deployment_address"],
            context["payment_asset"]["deployment_decimals"],
            context["payment_asset"]["pricing_decimals"],
        )
        if current != original:
            raise SettlementContextChanged()
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        ObjectDoesNotExist,
        SettlementAssetNotDeployedException,
    ) as exc:
        raise SettlementContextChanged() from exc
    return context


def settlement_execution_arguments(swap):
    context = recorded_settlement_context(swap)
    return {
        **context["typed_data"]["message"],
        "sellerSignature": swap.seller_signature,
        "buyerSignature": swap.buyer_signature,
        "settlement": {
            "protocol_version": context["protocol_version"],
            "swap_uuid": context["swap_uuid"],
            "digest": context["digest"],
            "domain": context["typed_data"]["domain"],
        },
    }
