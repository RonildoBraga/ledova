from datetime import timedelta

from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from tokens.models import SwapOrder
from tokens.services.settlement_context import capture_settlement_context

SYNTHETIC_SETTLEMENT_CONTRACT = "0x" + "9d" * 20


def save_swap_with_context(swap=None, **fields):
    swap = swap or SwapOrder(**fields)
    if swap.expires_at is None:
        swap.expires_at = timezone.now() + timedelta(hours=getattr(settings, "SWAP_ORDER_EXPIRY_HOURS", 0.25))
    with override_settings(ATOMIC_SWAP_ADDRESS=settings.ATOMIC_SWAP_ADDRESS or SYNTHETIC_SETTLEMENT_CONTRACT):
        capture_settlement_context(swap)
    swap.save()
    return swap
