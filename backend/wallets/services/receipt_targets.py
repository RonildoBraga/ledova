from typing import NamedTuple


class ReceiptTarget(NamedTuple):
    wallet: tuple
    transaction: tuple


def capture_receipt_target(wallet, tx):
    return ReceiptTarget(
        (wallet.pk, wallet.user_account_id, wallet.chain, wallet.address),
        tuple(getattr(tx, field.attname) for field in tx._meta.concrete_fields),
    )
