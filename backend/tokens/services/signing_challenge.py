import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from eth_utils import to_checksum_address

from shared.utils.typed_data import (
    build_domain,
    recover_typed_data_signer,
    typed_data_digest,
)
from tokens.exceptions import (
    ChallengeAlreadyUsedException,
    ChallengeExpiredException,
    ChallengeMismatchException,
    ChallengeUnknownException,
    InvalidSignatureException,
)
from tokens.models import SigningChallenge, SigningChallengePurpose

logger = logging.getLogger(__name__)

CHALLENGE_TYPES = {
    SigningChallengePurpose.ORDER_CANCEL: {
        "OrderCancel": [
            {"name": "orderUuid", "type": "string"},
            {"name": "wallet", "type": "address"},
            {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ]
    },
    SigningChallengePurpose.ORDER_CREATE: {
        "OrderCreate": [
            {"name": "tokenUuid", "type": "string"},
            {"name": "orderType", "type": "string"},
            {"name": "quantity", "type": "uint256"},
            {"name": "pricePerShare", "type": "string"},
            {"name": "wallet", "type": "address"},
            {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ]
    },
}


def challenge_lifetime_seconds() -> int:
    return getattr(settings, "SIGNING_CHALLENGE_TTL_SECONDS", 300)


def issue_challenge(purpose, wallet_address: str, fields: dict, verifying_contract=None, order=None):
    types = CHALLENGE_TYPES[purpose]
    wallet = to_checksum_address(wallet_address)
    nonce = secrets.randbits(63)
    expires_at = timezone.now() + timezone.timedelta(seconds=challenge_lifetime_seconds())

    message = {**fields, "wallet": wallet, "nonce": str(nonce), "deadline": str(int(expires_at.timestamp()))}
    domain = build_domain(settings.BLOCKCHAIN_CHAIN_ID, verifying_contract)

    return SigningChallenge.objects.create(
        purpose=purpose,
        wallet_address=wallet,
        chain_id=domain["chainId"],
        verifying_contract=domain["verifyingContract"],
        order=order,
        payload={"domain": domain, "types": types, "message": message},
        digest=typed_data_digest(domain, types, message),
        nonce=nonce,
        expires_at=expires_at,
    )


def challenge_response(challenge) -> dict:
    return {
        "digest": challenge.digest,
        "domain": challenge.payload["domain"],
        "types": challenge.payload["types"],
        "message": challenge.payload["message"],
        "expires_at": challenge.expires_at.isoformat(),
    }


def consume_challenge(digest: str, purpose, wallet_address: str, signature: str, order=None):
    if not digest or not signature:
        raise ChallengeUnknownException()

    challenge = SigningChallenge.objects.select_for_update().filter(digest=digest).first()
    if challenge is None:
        raise ChallengeUnknownException()

    if challenge.purpose != purpose:
        raise ChallengeMismatchException("action")

    if challenge.wallet_address.lower() != to_checksum_address(wallet_address).lower():
        raise ChallengeMismatchException("wallet")

    if order is not None and challenge.order_id != order.pk:
        raise ChallengeMismatchException("order")

    if challenge.chain_id != settings.BLOCKCHAIN_CHAIN_ID:
        raise ChallengeMismatchException("chain")

    if challenge.is_consumed:
        raise ChallengeAlreadyUsedException()

    if challenge.is_expired:
        raise ChallengeExpiredException()

    payload = challenge.payload
    signer = recover_typed_data_signer(payload["domain"], payload["types"], payload["message"], signature)
    if signer is None or signer.lower() != challenge.wallet_address.lower():
        raise InvalidSignatureException("The signature does not match the wallet this challenge was issued to.")

    return challenge


def assert_payload_matches(challenge, expected: dict) -> None:
    message = challenge.payload["message"]
    for field, value in expected.items():
        if str(message.get(field)) != str(value):
            raise ChallengeMismatchException("request")


def spend(challenge, signature: str) -> None:
    challenge.mark_consumed(signature)
    logger.info(f"Consumed {challenge.purpose} challenge for {challenge.wallet_address}")


@transaction.atomic
def purge_expired_challenges(cutoff=None) -> int:
    removed, _ = SigningChallenge.objects.expired_and_unspent(cutoff).delete()
    return removed
