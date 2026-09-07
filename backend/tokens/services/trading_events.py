from uuid import UUID

from asgiref.sync import sync_to_async

from tokens.models import ShareToken
from users.services.eligibility import investor_eligibility


def _is_eligible(user) -> bool:
    return investor_eligibility(user).is_eligible


async def resolve_streamable_token_uuid(user, raw_token_uuid):
    try:
        token_uuid = str(UUID(raw_token_uuid))
    except (AttributeError, TypeError, ValueError):
        return None

    if not await sync_to_async(_is_eligible)(user):
        return None

    if not await ShareToken.objects.deployed().filter(uuid=token_uuid).aexists():
        return None

    return token_uuid
