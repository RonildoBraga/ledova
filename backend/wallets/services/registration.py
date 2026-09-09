from django.db import IntegrityError
from rest_framework.exceptions import ValidationError

from shared.db import atomic
from wallets.constants import WALLET_VERIFICATION_STATUS_PENDING
from wallets.models import Wallet

DUPLICATE_WALLET = "This wallet address has already been added to your account on this network."


def _refuse_duplicate(wallet):
    matches = Wallet.objects.filter_by_address(wallet.address, chain=wallet.chain).filter(
        user_account_id=wallet.user_account_id
    )
    if not wallet._state.adding:
        matches = matches.exclude(pk=wallet.pk)
    if matches.exists():
        raise ValidationError({"address": DUPLICATE_WALLET}) from None


def register_wallet(user, **fields):
    wallet = Wallet(**fields, verification_status=WALLET_VERIFICATION_STATUS_PENDING)
    try:
        with atomic():
            wallet.save(force_insert=True)
            preferences = getattr(getattr(user, "userprofile", None), "preferences", None)
            portfolio = preferences.selected_portfolio if preferences else None
            if portfolio and portfolio.user_account_id == wallet.user_account_id:
                portfolio.wallets.add(wallet)
    except IntegrityError:
        _refuse_duplicate(wallet)
        raise
    return wallet


def update_wallet(wallet, fields):
    for name, value in fields.items():
        setattr(wallet, name, value)
    try:
        with atomic():
            wallet.save()
    except IntegrityError:
        _refuse_duplicate(wallet)
        raise
    return wallet
