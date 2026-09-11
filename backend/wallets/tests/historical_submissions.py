from decimal import Decimal, localcontext
from uuid import uuid4

from django.utils import timezone

from tokens.services.signed_transactions import decode_signed_transaction


def native_submission_at(apps, wallet, asset, signed, *, status="pending"):
    raw = bytes(signed.raw_transaction)
    decoded = decode_signed_transaction(raw)
    price = decoded.max_fee_per_gas if decoded.envelope_type == 2 else decoded.gas_price
    with localcontext() as context:
        context.prec = 90
        amount = Decimal(decoded.value).scaleb(-18)
        fee = Decimal(decoded.gas_limit * price).scaleb(-18)
    holding = apps.get_model("wallets", "Holding").objects.get(wallet_id=wallet.pk, asset_id=asset.pk)
    tx = apps.get_model("wallets", "Transaction").objects.create(
        wallet_id=wallet.pk,
        user_account_id=wallet.user_account_id,
        asset_id=asset.pk,
        tx_hash=signed.hash.to_0x_hex(),
        chain=wallet.chain,
        from_address=wallet.address,
        to_address=decoded.to,
        amount=amount,
        nonce=decoded.nonce,
        status="pending",
        transaction_fee_estimated=fee,
        deducted_amount=amount + fee,
        deducted_amount_sync_version=holding.sync_version,
    )
    holding.quantity -= amount + fee
    holding.balance_version = uuid4()
    holding.save(update_fields=["quantity", "balance_version", "updated_at"])
    apps.get_model("wallets", "HoldingSnapshot").objects.update_or_create(
        holding=holding,
        snapshot_date=timezone.now().date(),
        defaults={"quantity": holding.quantity, "snapshot_reason": "transaction"},
    )
    intent = {
        "mined_nonce_observation": {
            "chain_id": decoded.chain_id,
            "nonce": 0,
            "balance_wei": str(10 * 10**18),
            "block_number": 100,
            "block_hash": "0x" + "ab" * 32,
        },
        "to_address": decoded.to,
        "amount": str(amount),
        "token_contract": None,
        "asset_decimals": 18,
        "raw_amount": str(decoded.value),
        "maximum_fee": str(fee),
        "envelope_type": decoded.envelope_type,
        "envelope_to": decoded.to,
        "value": str(decoded.value),
        "gas_limit": str(decoded.gas_limit),
        "gas_price": str(decoded.gas_price) if decoded.gas_price is not None else None,
        "max_fee_per_gas": str(decoded.max_fee_per_gas) if decoded.max_fee_per_gas is not None else None,
        "max_priority_fee_per_gas": (
            str(decoded.max_priority_fee_per_gas) if decoded.max_priority_fee_per_gas is not None else None
        ),
    }
    submission = apps.get_model("wallets", "WalletSubmission").objects.create(
        wallet_id=wallet.pk,
        user_account_id=wallet.user_account_id,
        transaction_id=tx.pk,
        asset_id=asset.pk,
        chain=wallet.chain,
        chain_id=decoded.chain_id,
        sender_address=decoded.sender.lower(),
        nonce=decoded.nonce,
        tx_hash=signed.hash.to_0x_hex(),
        raw_transaction=raw,
        intent=intent,
    )
    if status != "pending":
        tx.status = status
        tx.save(update_fields=["status"])
    return submission


def historical_financial_state(apps):
    return tuple(
        list(apps.get_model("wallets", name).objects.order_by("pk").values())
        for name in ("Transaction", "Holding", "HoldingSnapshot")
    )
