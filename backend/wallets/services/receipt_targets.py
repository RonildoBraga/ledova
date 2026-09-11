from typing import NamedTuple


class ReceiptTarget(NamedTuple):
    wallet: tuple
    transaction: tuple
    family: tuple | None = None


def capture_receipt_target(wallet, tx):
    from wallets.models import WalletSubmission

    family = (
        WalletSubmission.objects.filter(transaction=tx)
        .values_list("family_id", "family__generation", "family__selected_id", "family__winner_id")
        .first()
    )
    return ReceiptTarget(
        (wallet.pk, wallet.user_account_id, wallet.chain, wallet.address),
        tuple(getattr(tx, field.attname) for field in tx._meta.concrete_fields),
        family,
    )
