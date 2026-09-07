import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.exceptions import (
    InvalidSignatureException,
    SignatureRequiredException,
    VerificationChallengeNotFoundException,
)
from wallets.models import Wallet
from wallets.services.wallets import (
    generate_verification_challenge,
    verify_wallet_signature,
)

logger = logging.getLogger(__name__)


def _locked_wallet(user, uuid):
    return get_object_or_404(
        Wallet.objects.visible_to_user(user).select_for_update(of=("self",)),
        uuid=uuid,
    )


@transaction.atomic
def start_wallet_verification(user, uuid):
    wallet = _locked_wallet(user, uuid)
    wallet.verification_challenge = generate_verification_challenge(wallet.address)
    wallet.save(update_fields=["verification_challenge"])
    return wallet


@transaction.atomic
def complete_wallet_verification(user, uuid, signature):
    wallet = _locked_wallet(user, uuid)

    if not signature:
        raise SignatureRequiredException()

    if not wallet.verification_challenge:
        raise VerificationChallengeNotFoundException()

    if not verify_wallet_signature(wallet.address, wallet.verification_challenge, signature, wallet.chain.upper()):
        raise InvalidSignatureException()

    wallet.verification_status = WALLET_VERIFICATION_STATUS_VERIFIED
    wallet.verification_signature = signature
    wallet.verified_at = timezone.now()
    wallet.verification_challenge = None
    wallet.save(
        update_fields=["verification_status", "verification_signature", "verified_at", "verification_challenge"]
    )

    _queue_sync(wallet)
    return wallet


def _queue_sync(wallet):
    from wallets.tasks import sync_wallet

    try:
        sync_wallet.defer(wallet_uuid=str(wallet.uuid))
    except Exception:
        logger.error(f"Failed to queue a sync for wallet {wallet.uuid} after verification", exc_info=True)
