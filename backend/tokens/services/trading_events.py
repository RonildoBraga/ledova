from uuid import UUID

from tokens.models import ShareToken


async def resolve_deployed_token_uuid(raw_token_uuid):
    try:
        token_uuid = str(UUID(raw_token_uuid))
    except (AttributeError, TypeError, ValueError):
        return None

    if not await ShareToken.objects.deployed().filter(uuid=token_uuid).aexists():
        return None

    return token_uuid
